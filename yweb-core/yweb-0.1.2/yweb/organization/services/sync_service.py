"""
组织管理模块 - 同步服务基类

提供从外部系统（企业微信、飞书、钉钉等）同步组织数据的抽象接口

设计说明：
- 不使用泛型，避免 IDE 类型推断问题
- 子类通过类属性指定具体的模型类

安全同步机制：
- 预拉取：一次性获取外部数据并缓存，避免重复 API 调用和数据不一致窗口
- 安全阈值：外部数据异常（为空/骤减）时中止同步，防止误删
- 软删除部门：本地多出的部门设置 deleted_at，不物理删除
- 标记离职：本地多出的员工标记为离职状态，保留历史数据和用户关联
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Type, Optional, List, Dict, Any

from yweb.orm import BaseModel
from ..enums import ExternalSource, EmployeeStatus, SyncStatus


class SyncResult:
    """同步结果"""
    
    def __init__(self):
        self.success: bool = True
        self.message: str = ""
        self.created_count: int = 0
        self.updated_count: int = 0
        self.deleted_count: int = 0
        self.skipped_count: int = 0
        self.errors: List[str] = []
        self.start_time: datetime = datetime.now()
        self.end_time: Optional[datetime] = None
    
    def add_error(self, error: str):
        """添加错误信息"""
        self.errors.append(error)
        self.success = False
    
    def finish(self, message: str = ""):
        """完成同步"""
        self.end_time = datetime.now()
        self.message = message
    
    @property
    def duration_seconds(self) -> float:
        """获取同步耗时（秒）"""
        if self.end_time is None:
            return 0
        return (self.end_time - self.start_time).total_seconds()
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "success": self.success,
            "message": self.message,
            "created_count": self.created_count,
            "updated_count": self.updated_count,
            "deleted_count": self.deleted_count,
            "skipped_count": self.skipped_count,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
        }


class BaseSyncService(ABC):
    """同步服务基类
    
    提供从外部系统同步组织数据的抽象接口。
    子类需要实现具体的同步逻辑。
    
    主要功能：
    - 同步组织信息
    - 同步部门数据（包括树形结构）
    - 同步员工数据
    - 同步员工-部门关系
    
    使用示例:
        from yweb.organization import BaseSyncService, ExternalSource
        
        class WechatWorkSyncService(BaseSyncService):
            external_source = ExternalSource.WECHAT_WORK
            
            def fetch_departments(self, org) -> List[dict]:
                # 调用企业微信 API 获取部门列表
                ...
            
            def fetch_employees(self, org) -> List[dict]:
                # 调用企业微信 API 获取员工列表
                ...
    """
    
    # ==================== 配置（子类必须/可选设置） ====================
    
    # 外部系统来源（子类必须设置）
    external_source: ExternalSource = None
    
    # 模型类（子类必须设置）
    org_model: Type[BaseModel] = None
    dept_model: Type[BaseModel] = None
    employee_model: Type[BaseModel] = None
    emp_org_rel_model: Type[BaseModel] = None
    emp_dept_rel_model: Type[BaseModel] = None
    
    def __init__(self):
        """初始化服务，校验配置"""
        # 预拉取缓存（在 sync_from_external 中一次性填充，避免重复 API 调用）
        self._cached_departments: Optional[List[Dict[str, Any]]] = None
        self._cached_employees: Optional[List[Dict[str, Any]]] = None
        self._validate_config()
    
    def _validate_config(self):
        """校验配置"""
        if self.external_source is None:
            raise ValueError("请在子类中设置 external_source")
        
        required_models = [
            ('org_model', self.org_model),
            ('dept_model', self.dept_model),
            ('employee_model', self.employee_model),
            ('emp_org_rel_model', self.emp_org_rel_model),
            ('emp_dept_rel_model', self.emp_dept_rel_model),
        ]
        
        missing = [name for name, model in required_models if model is None]
        if missing:
            raise ValueError(f"请在子类中配置以下模型类: {', '.join(missing)}")
    
    # ==================== 主同步方法 ====================
    
    def sync_from_external(self, org_id: int) -> SyncResult:
        """从外部系统同步完整数据
        
        安全同步流程：
        1. 一次性预拉取外部数据并缓存（避免重复 API 调用）
        2. 安全阈值检查（防止 API 故障导致误删全部数据）
        3. 按顺序同步：组织信息 → 部门 → 员工 → 员工-部门关系
        4. 清理缓存
        
        Args:
            org_id: 组织ID
            
        Returns:
            同步结果
        """
        result = SyncResult()
        
        try:
            org = self.org_model.get(org_id)
            if org is None:
                result.add_error(f"组织不存在: {org_id}")
                return result
            
            # 校验外部来源
            if org.external_source != self.external_source.value:
                result.add_error(
                    f"组织的外部来源({org.external_source})与同步服务({self.external_source.value})不匹配"
                )
                return result
            
            # 一次性预拉取外部数据并缓存
            self._cached_departments = self.fetch_departments(org)
            self._cached_employees = self.fetch_employees(org)
            
            # 安全阈值检查
            local_dept_count = self.dept_model.query.filter(
                self.dept_model.org_id == org.id
            ).count()
            local_emp_count = self.emp_org_rel_model.query.filter(
                self.emp_org_rel_model.org_id == org.id
            ).count()
            self._check_safety_threshold(
                local_dept_count, len(self._cached_departments), "部门", result
            )
            self._check_safety_threshold(
                local_emp_count, len(self._cached_employees), "员工", result
            )
            if not result.success:
                result.finish("安全检查未通过，同步中止")
                return result
            
            # 1. 同步组织信息
            org_result = self.sync_organization(org)
            if not org_result.success:
                result.errors.extend(org_result.errors)
            
            # 2. 同步部门
            dept_result = self.sync_departments(org)
            result.created_count += dept_result.created_count
            result.updated_count += dept_result.updated_count
            result.deleted_count += dept_result.deleted_count
            if not dept_result.success:
                result.errors.extend(dept_result.errors)
            
            # 3. 同步员工
            emp_result = self.sync_employees(org)
            result.created_count += emp_result.created_count
            result.updated_count += emp_result.updated_count
            result.deleted_count += emp_result.deleted_count
            if not emp_result.success:
                result.errors.extend(emp_result.errors)
            
            # 4. 同步员工-部门关系
            rel_result = self.sync_employee_dept_relations(org)
            if not rel_result.success:
                result.errors.extend(rel_result.errors)
            
            result.success = len(result.errors) == 0
            result.finish("同步完成" if result.success else "同步完成，但有错误")
            
        except Exception as e:
            result.add_error(f"同步异常: {str(e)}")
            result.finish("同步失败")
        finally:
            # 清理缓存
            self._cached_departments = None
            self._cached_employees = None
        
        return result
    
    def _check_safety_threshold(
        self, local_count: int, external_count: int, label: str, result: SyncResult
    ):
        """安全阈值检查
        
        防止外部 API 故障（返回空列表/部分数据）导致误删大量本地数据。
        
        规则：
        - 本地 > 10 条且外部为 0 → 疑似 API 故障，中止
        - 本地 > 20 条且外部 < 本地的 30% → 疑似数据异常，中止
        - 首次同步（本地为 0）→ 跳过检查
        """
        if local_count == 0:
            return  # 首次同步，无需检查
        
        if local_count > 10 and external_count == 0:
            result.add_error(
                f"外部{label}数据为空但本地有 {local_count} 条，"
                f"疑似 API 故障，中止同步（如需强制同步请先手动清理）"
            )
        elif local_count > 20 and external_count < local_count * 0.3:
            result.add_error(
                f"外部{label}({external_count}条)远少于本地({local_count}条)，"
                f"疑似数据异常，中止同步"
            )
    
    # ==================== 抽象方法（子类必须实现） ====================
    
    @abstractmethod
    def fetch_departments(self, org: BaseModel) -> List[Dict[str, Any]]:
        """从外部系统获取部门列表
        
        Args:
            org: 组织对象
            
        Returns:
            部门数据列表，每个元素应包含：
            - external_dept_id: 外部部门ID
            - external_parent_id: 外部父部门ID
            - name: 部门名称
            - sort_order: 排序（可选）
            - ... 其他字段
        """
        pass
    
    @abstractmethod
    def fetch_employees(self, org: BaseModel) -> List[Dict[str, Any]]:
        """从外部系统获取员工列表
        
        Args:
            org: 组织对象
            
        Returns:
            员工数据列表，每个元素应包含：
            - external_user_id: 外部用户ID
            - name: 姓名
            - mobile: 手机号（可选）
            - email: 邮箱（可选）
            - department_ids: 所属部门的外部ID列表
            - ... 其他字段
        """
        pass
    
    @abstractmethod
    def fetch_organization_info(self, org: BaseModel) -> Optional[Dict[str, Any]]:
        """从外部系统获取组织信息
        
        Args:
            org: 组织对象
            
        Returns:
            组织信息字典，如果获取失败返回 None
        """
        pass
    
    # ==================== 同步逻辑（可被子类重写） ====================
    
    def sync_organization(self, org: BaseModel) -> SyncResult:
        """同步组织信息
        
        Args:
            org: 组织对象
            
        Returns:
            同步结果
        """
        result = SyncResult()
        
        try:
            info = self.fetch_organization_info(org)
            if info:
                # 更新组织信息
                for key, value in info.items():
                    if hasattr(org, key) and key not in ['id', 'external_source', 'external_corp_id']:
                        setattr(org, key, value)
                org.save(commit=True)
                result.updated_count = 1
            
            result.finish()
        except Exception as e:
            result.add_error(f"同步组织信息失败: {str(e)}")
        
        return result
    
    def sync_departments(self, org: BaseModel) -> SyncResult:
        """同步部门数据
        
        安全 upsert 策略：
        - 基于 external_dept_id 映射关系逐条更新或创建
        - 本地多出的部门执行软删除（设置 deleted_at），不物理删除
        - 两遍遍历：先创建/更新，再建立父子关系（避免循环依赖）
        
        Args:
            org: 组织对象
            
        Returns:
            同步结果
        """
        result = SyncResult()
        
        try:
            # 使用缓存数据（由 sync_from_external 预拉取）
            external_depts = self._cached_departments or self.fetch_departments(org)
            
            # 建立外部ID到部门数据的映射
            external_dept_map = {
                str(d['external_dept_id']): d for d in external_depts
            }
            
            # 获取现有部门（按external_dept_id索引）
            existing_depts = self.dept_model.query.filter(
                self.dept_model.org_id == org.id
            ).all()
            existing_dept_map = {
                d.external_dept_id: d for d in existing_depts if d.external_dept_id
            }
            
            # 同步部门（先处理所有部门，再建立父子关系）
            synced_depts = {}  # external_dept_id -> dept
            
            # 第一遍：创建/更新部门（暂不设置parent_id）
            for ext_id, data in external_dept_map.items():
                if ext_id in existing_dept_map:
                    # 更新
                    dept = existing_dept_map[ext_id]
                    self._update_dept_from_external(dept, data)
                    result.updated_count += 1
                else:
                    # 创建
                    dept = self._create_dept_from_external(org, data)
                    result.created_count += 1
                
                synced_depts[ext_id] = dept
            
            # 第二遍：建立父子关系
            for ext_id, data in external_dept_map.items():
                dept = synced_depts[ext_id]
                ext_parent_id = str(data.get('external_parent_id', '')) if data.get('external_parent_id') else None
                
                if ext_parent_id and ext_parent_id in synced_depts:
                    parent = synced_depts[ext_parent_id]
                    if dept.parent_id != parent.id:
                        dept.parent_id = parent.id
                        dept.update_path_and_level()
                        dept.save(commit=True)
                elif dept.parent_id is not None:
                    # 变成根部门
                    dept.parent_id = None
                    dept.update_path_and_level()
                    dept.save(commit=True)
            
            # 本地有、外部没有的部门 → 软删除（设置 deleted_at）
            for ext_id, dept in existing_dept_map.items():
                if ext_id not in external_dept_map:
                    dept.deleted_at = datetime.now()
                    dept.save(commit=True)
                    result.deleted_count += 1
            
            result.finish()
        except Exception as e:
            result.add_error(f"同步部门失败: {str(e)}")
        
        return result
    
    def sync_employees(self, org: BaseModel) -> SyncResult:
        """同步员工数据
        
        安全 upsert 策略：
        - 基于 external_user_id 映射关系逐条更新或创建
        - 本地多出的员工标记为离职（status=RESIGNED），不删除记录
        - 保留 Employee 和关联的 User 记录，仅清理部门关联
        
        Args:
            org: 组织对象
            
        Returns:
            同步结果
        """
        result = SyncResult()
        
        try:
            # 使用缓存数据（由 sync_from_external 预拉取）
            external_emps = self._cached_employees or self.fetch_employees(org)
            
            # 建立外部ID映射
            external_emp_map = {
                str(e['external_user_id']): e for e in external_emps
            }
            
            # 获取现有员工-组织关联
            existing_rels = self.emp_org_rel_model.query.filter(
                self.emp_org_rel_model.org_id == org.id
            ).all()
            existing_rel_map = {
                r.external_user_id: r for r in existing_rels if r.external_user_id
            }
            
            # 同步员工
            for ext_id, data in external_emp_map.items():
                if ext_id in existing_rel_map:
                    # 更新（基于映射关系确定是同一个人）
                    rel = existing_rel_map[ext_id]
                    employee = self.employee_model.get(rel.employee_id)
                    if employee:
                        self._update_employee_from_external(employee, rel, data)
                        # 如果之前被标记为离职，恢复为外部数据中的状态
                        if hasattr(rel, 'status') and rel.status == EmployeeStatus.RESIGNED.value:
                            rel.status = data.get('status', EmployeeStatus.ACTIVE.value)
                            rel.save(commit=True)
                        result.updated_count += 1
                else:
                    # 创建
                    self._create_employee_from_external(org, data)
                    result.created_count += 1
            
            # 本地有、外部没有的员工 → 标记离职（保留记录和用户关联）
            for ext_id, rel in existing_rel_map.items():
                if ext_id not in external_emp_map:
                    if hasattr(rel, 'status'):
                        rel.status = EmployeeStatus.RESIGNED.value
                        rel.save(commit=True)
                    # 清理部门关联
                    self.emp_dept_rel_model.query.filter(
                        self.emp_dept_rel_model.employee_id == rel.employee_id
                    ).delete()
                    # 钩子：子类可覆写以执行额外操作（如禁用关联用户账号）
                    employee = self.employee_model.get(rel.employee_id)
                    if employee:
                        self._on_employee_mark_resigned(employee, rel)
                    result.deleted_count += 1
            
            result.finish()
        except Exception as e:
            result.add_error(f"同步员工失败: {str(e)}")
        
        return result
    
    def sync_employee_dept_relations(self, org: BaseModel) -> SyncResult:
        """同步员工-部门关系
        
        Args:
            org: 组织对象
            
        Returns:
            同步结果
        """
        result = SyncResult()
        
        try:
            # 使用缓存数据（避免重复 API 调用）
            external_emps = self._cached_employees or self.fetch_employees(org)
            
            # 建立外部部门ID到内部部门ID的映射
            depts = self.dept_model.query.filter(
                self.dept_model.org_id == org.id
            ).all()
            ext_to_dept_id = {
                d.external_dept_id: d.id for d in depts if d.external_dept_id
            }
            
            # 建立外部用户ID到员工ID的映射
            rels = self.emp_org_rel_model.query.filter(
                self.emp_org_rel_model.org_id == org.id
            ).all()
            ext_to_employee_id = {
                r.external_user_id: r.employee_id for r in rels if r.external_user_id
            }
            
            # 同步关系
            for emp_data in external_emps:
                ext_user_id = str(emp_data.get('external_user_id', ''))
                employee_id = ext_to_employee_id.get(ext_user_id)
                
                if not employee_id:
                    continue
                
                # 获取外部部门ID列表
                ext_dept_ids = emp_data.get('department_ids', [])
                if isinstance(ext_dept_ids, str):
                    ext_dept_ids = [ext_dept_ids]
                ext_dept_ids = [str(d) for d in ext_dept_ids]
                
                # 转换为内部部门ID
                target_dept_ids = set()
                for ext_dept_id in ext_dept_ids:
                    if ext_dept_id in ext_to_dept_id:
                        target_dept_ids.add(ext_to_dept_id[ext_dept_id])
                
                # 获取现有关系
                existing_rels = self.emp_dept_rel_model.query.filter(
                    self.emp_dept_rel_model.employee_id == employee_id,
                    self.emp_dept_rel_model.dept_id.in_(list(ext_to_dept_id.values()))
                ).all()
                current_dept_ids = {r.dept_id for r in existing_rels}
                
                # 添加新关系
                for dept_id in target_dept_ids - current_dept_ids:
                    rel = self.emp_dept_rel_model(
                        employee_id=employee_id,
                        dept_id=dept_id,
                        external_dept_id=next(
                            (k for k, v in ext_to_dept_id.items() if v == dept_id),
                            None
                        )
                    )
                    rel.save(commit=True)
                
                # 删除多余关系
                for dept_id in current_dept_ids - target_dept_ids:
                    self.emp_dept_rel_model.query.filter(
                        self.emp_dept_rel_model.employee_id == employee_id,
                        self.emp_dept_rel_model.dept_id == dept_id
                    ).delete()
            
            result.finish()
        except Exception as e:
            result.add_error(f"同步员工-部门关系失败: {str(e)}")
        
        return result
    
    # ==================== 辅助方法（可被子类重写） ====================
    
    def _create_dept_from_external(self, org: BaseModel, data: Dict[str, Any]) -> BaseModel:
        """根据外部数据创建部门
        
        子类可重写以处理特殊字段
        """
        dept = self.dept_model(
            org_id=org.id,
            name=data.get('name', ''),
            external_dept_id=str(data.get('external_dept_id', '')),
            external_parent_id=str(data.get('external_parent_id', '')) if data.get('external_parent_id') else None,
            sort_order=data.get('sort_order', 0),
        )
        dept.update_path_and_level()
        dept.save(commit=True)
        return dept
    
    def _update_dept_from_external(self, dept: BaseModel, data: Dict[str, Any]):
        """根据外部数据更新部门
        
        子类可重写以处理特殊字段
        """
        dept.name = data.get('name', dept.name)
        dept.external_parent_id = str(data.get('external_parent_id', '')) if data.get('external_parent_id') else None
        dept.sort_order = data.get('sort_order', dept.sort_order)
        dept.save(commit=True)
    
    def _create_employee_from_external(self, org: BaseModel, data: Dict[str, Any]) -> BaseModel:
        """根据外部数据创建员工
        
        子类可重写以处理特殊字段
        """
        # 创建员工
        employee = self.employee_model(
            name=data.get('name', ''),
            mobile=data.get('mobile'),
            email=data.get('email'),
            avatar=data.get('avatar'),
            gender=data.get('gender', 0),
        )
        employee.save(commit=True)
        
        # 创建员工-组织关联
        rel = self.emp_org_rel_model(
            employee_id=employee.id,
            org_id=org.id,
            emp_no=data.get('emp_no'),
            position=data.get('position'),
            external_user_id=str(data.get('external_user_id', '')),
            external_union_id=data.get('external_union_id'),
        )
        rel.save(commit=True)
        
        return employee
    
    def _update_employee_from_external(
        self,
        employee: BaseModel,
        rel: BaseModel,
        data: Dict[str, Any]
    ):
        """根据外部数据更新员工
        
        子类可重写以处理特殊字段
        """
        employee.name = data.get('name', employee.name)
        employee.mobile = data.get('mobile', employee.mobile)
        employee.email = data.get('email', employee.email)
        employee.avatar = data.get('avatar', employee.avatar)
        employee.gender = data.get('gender', employee.gender)
        employee.save(commit=True)
        
        rel.emp_no = data.get('emp_no', rel.emp_no)
        rel.position = data.get('position', rel.position)
        rel.external_union_id = data.get('external_union_id', rel.external_union_id)
        rel.save(commit=True)
    
    # ==================== 生命周期钩子（子类可覆写） ====================
    
    def _on_employee_mark_resigned(self, employee: BaseModel, rel: BaseModel):
        """钩子：员工被标记为离职时调用
        
        子类可覆写以执行额外操作，例如禁用关联的用户账号。
        默认不做任何操作。
        
        Args:
            employee: 员工实体
            rel: 员工-组织关联实体
        """
        pass


__all__ = ["BaseSyncService", "SyncResult"]
