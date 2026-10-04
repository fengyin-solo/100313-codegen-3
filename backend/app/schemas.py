"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None
    received: dict[str, Any] | None = None
    existing: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None



class MineareaEntry(BaseModel):
    """矿区明细结构。"""

    field_0: str | None = None  # 矿区编号
    field_1: str | None = None  # 矿区名称
    field_2: str | None = None  # 开采矿种
    field_3: str | None = None  # 核定产能
    field_4: str | None = None  # 开采方式
    field_5: str | None = None  # 服务年限
    field_6: str | None = None  # 安全等级
    field_7: str | None = None  # 矿区状态

class GasEntry(BaseModel):
    """瓦斯测点明细结构。"""

    field_0: str | None = None  # 测点编号
    field_1: str | None = None  # 所在区域
    field_2: str | None = None  # 瓦斯浓度
    field_3: str | None = None  # 一氧化碳浓度
    field_4: str | None = None  # 温度
    field_5: str | None = None  # 风速
    field_6: str | None = None  # 监测时刻
    field_7: str | None = None  # 测点状态

class VentilationEntry(BaseModel):
    """通风设备明细结构。"""

    field_0: str | None = None  # 设备编号
    field_1: str | None = None  # 设备类型
    field_2: str | None = None  # 额定风量
    field_3: str | None = None  # 运行频率
    field_4: str | None = None  # 电流值
    field_5: str | None = None  # 所属巷道
    field_6: str | None = None  # 上次检修
    field_7: str | None = None  # 设备状态

class RoofEntry(BaseModel):
    """顶板监测明细结构。"""

    field_0: str | None = None  # 监测编号
    field_1: str | None = None  # 所在工作面
    field_2: str | None = None  # 离层量
    field_3: str | None = None  # 锚杆受力
    field_4: str | None = None  # 收敛变形
    field_5: str | None = None  # 监测日期
    field_6: str | None = None  # 监测人员
    field_7: str | None = None  # 顶板状态

class WaterhazardEntry(BaseModel):
    """水文监测明细结构。"""

    field_0: str | None = None  # 监测编号
    field_1: str | None = None  # 所在区域
    field_2: str | None = None  # 涌水量
    field_3: str | None = None  # 水压
    field_4: str | None = None  # 水温
    field_5: str | None = None  # 水质类型
    field_6: str | None = None  # 排水能力
    field_7: str | None = None  # 水害状态

class RockburstEntry(BaseModel):
    """微震监测明细结构。"""

    field_0: str | None = None  # 监测编号
    field_1: str | None = None  # 所在区域
    field_2: str | None = None  # 微震能量
    field_3: str | None = None  # 微震频次
    field_4: str | None = None  # 应力值
    field_5: str | None = None  # 预警等级
    field_6: str | None = None  # 处置措施
    field_7: str | None = None  # 监测状态

class PersonnelEntry(BaseModel):
    """定位终端明细结构。"""

    field_0: str | None = None  # 终端编号
    field_1: str | None = None  # 携带人员
    field_2: str | None = None  # 所在位置
    field_3: str | None = None  # 入井时刻
    field_4: str | None = None  # 区域停留
    field_5: str | None = None  # 定位精度
    field_6: str | None = None  # 信号强度
    field_7: str | None = None  # 终端状态

class DustEntry(BaseModel):
    """粉尘测点明细结构。"""

    field_0: str | None = None  # 测点编号
    field_1: str | None = None  # 所在区域
    field_2: str | None = None  # 粉尘浓度
    field_3: str | None = None  # 游离二氧化硅
    field_4: str | None = None  # 降尘措施
    field_5: str | None = None  # 降尘效率
    field_6: str | None = None  # 监测日期
    field_7: str | None = None  # 测点状态

class FirepreventEntry(BaseModel):
    """防火监测明细结构。"""

    field_0: str | None = None  # 监测编号
    field_1: str | None = None  # 所在区域
    field_2: str | None = None  # 束管监测
    field_3: str | None = None  # 标志气体
    field_4: str | None = None  # 温度异常
    field_5: str | None = None  # 注浆量
    field_6: str | None = None  # 注氮量
    field_7: str | None = None  # 防火状态

class BeltEntry(BaseModel):
    """运输皮带明细结构。"""

    field_0: str | None = None  # 皮带编号
    field_1: str | None = None  # 所属巷道
    field_2: str | None = None  # 运输长度
    field_3: str | None = None  # 带速
    field_4: str | None = None  # 运量
    field_5: str | None = None  # 保护装置
    field_6: str | None = None  # 巡检日期
    field_7: str | None = None  # 皮带状态

class HoistEntry(BaseModel):
    """提升机明细结构。"""

    field_0: str | None = None  # 提升机编号
    field_1: str | None = None  # 提升类型
    field_2: str | None = None  # 提升高度
    field_3: str | None = None  # 额定载荷
    field_4: str | None = None  # 钢丝绳直径
    field_5: str | None = None  # 上次探伤
    field_6: str | None = None  # 制动系统
    field_7: str | None = None  # 提升状态

class PowerEntry(BaseModel):
    """供电设备明细结构。"""

    field_0: str | None = None  # 设备编号
    field_1: str | None = None  # 设备类型
    field_2: str | None = None  # 电压等级
    field_3: str | None = None  # 所属区域
    field_4: str | None = None  # 运行负荷
    field_5: str | None = None  # 绝缘电阻
    field_6: str | None = None  # 上次试验
    field_7: str | None = None  # 设备状态

class RescueEntry(BaseModel):
    """救援装备明细结构。"""

    field_0: str | None = None  # 装备编号
    field_1: str | None = None  # 装备名称
    field_2: str | None = None  # 装备类别
    field_3: str | None = None  # 存放地点
    field_4: str | None = None  # 保有数量
    field_5: str | None = None  # 上次检查
    field_6: str | None = None  # 下次检查日
    field_7: str | None = None  # 装备状态

class TrainingEntry(BaseModel):
    """培训记录明细结构。"""

    field_0: str | None = None  # 培训编号
    field_1: str | None = None  # 培训主题
    field_2: str | None = None  # 培训对象
    field_3: str | None = None  # 培训日期
    field_4: str | None = None  # 培训讲师
    field_5: str | None = None  # 考核方式
    field_6: str | None = None  # 考核结果
    field_7: str | None = None  # 培训状态

class ShiftEntry(BaseModel):
    """入井记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 入井人员
    field_2: str | None = None  # 所属班组
    field_3: str | None = None  # 入井时间
    field_4: str | None = None  # 升井时间
    field_5: str | None = None  # 携带设备
    field_6: str | None = None  # 出勤区域
    field_7: str | None = None  # 入井状态

class ExplosiveEntry(BaseModel):
    """爆破记录明细结构。"""

    field_0: str | None = None  # 爆破编号
    field_1: str | None = None  # 爆破区域
    field_2: str | None = None  # 炸药用量
    field_3: str | None = None  # 雷管用量
    field_4: str | None = None  # 爆破时间
    field_5: str | None = None  # 警戒范围
    field_6: str | None = None  # 爆破人员
    field_7: str | None = None  # 爆破状态

class RoadwayEntry(BaseModel):
    """维修任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 维修巷道
    field_2: str | None = None  # 维修内容
    field_3: str | None = None  # 施工队伍
    field_4: str | None = None  # 开工日期
    field_5: str | None = None  # 竣工日期
    field_6: str | None = None  # 验收人员
    field_7: str | None = None  # 任务状态

class MonitorstationEntry(BaseModel):
    """监测分站明细结构。"""

    field_0: str | None = None  # 分站编号
    field_1: str | None = None  # 分站名称
    field_2: str | None = None  # 所在位置
    field_3: str | None = None  # 通信地址
    field_4: str | None = None  # 接入传感器
    field_5: str | None = None  # 信号强度
    field_6: str | None = None  # 后备电源
    field_7: str | None = None  # 分站状态

class CertificateEntry(BaseModel):
    """持证人员明细结构。"""

    field_0: str | None = None  # 人员编号
    field_1: str | None = None  # 姓名
    field_2: str | None = None  # 证书类别
    field_3: str | None = None  # 证书编号
    field_4: str | None = None  # 发证日期
    field_5: str | None = None  # 到期日期
    field_6: str | None = None  # 复训记录
    field_7: str | None = None  # 证书状态

class EmergencydrillEntry(BaseModel):
    """演练记录明细结构。"""

    field_0: str | None = None  # 演练编号
    field_1: str | None = None  # 演练主题
    field_2: str | None = None  # 演练区域
    field_3: str | None = None  # 参演人数
    field_4: str | None = None  # 演练日期
    field_5: str | None = None  # 演练评估
    field_6: str | None = None  # 改进措施
    field_7: str | None = None  # 演练状态
