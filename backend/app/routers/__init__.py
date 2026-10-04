"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import minearea as router_minearea
from app.routers import gas as router_gas
from app.routers import ventilation as router_ventilation
from app.routers import roof as router_roof
from app.routers import waterhazard as router_waterhazard
from app.routers import rockburst as router_rockburst
from app.routers import personnel as router_personnel
from app.routers import dust as router_dust
from app.routers import fireprevent as router_fireprevent
from app.routers import belt as router_belt
from app.routers import hoist as router_hoist
from app.routers import power as router_power
from app.routers import rescue as router_rescue
from app.routers import training as router_training
from app.routers import shift as router_shift
from app.routers import explosive as router_explosive
from app.routers import roadway as router_roadway
from app.routers import monitorstation as router_monitorstation
from app.routers import certificate as router_certificate
from app.routers import emergencydrill as router_emergencydrill
from app.routers import safetyfee as router_safetyfee

ROUTERS = [router_minearea, router_gas, router_ventilation, router_roof, router_waterhazard, router_rockburst, router_personnel, router_dust, router_fireprevent, router_belt, router_hoist, router_power, router_rescue, router_training, router_shift, router_explosive, router_roadway, router_monitorstation, router_certificate, router_emergencydrill, router_safetyfee]
