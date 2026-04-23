"""
API路由模块
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)
map_bp = Blueprint('map', __name__)
scene_bp = Blueprint('scene', __name__)
control_bp = Blueprint('control', __name__)

from . import graph  # noqa: E402, F401
from . import simulation  # noqa: E402, F401
from . import report  # noqa: E402, F401
from . import map_seed  # noqa: E402, F401
from . import scene_material  # noqa: E402, F401
from . import control  # noqa: E402, F401
