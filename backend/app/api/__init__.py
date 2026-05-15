from flask import Blueprint

graph_bp = Blueprint("graph", __name__)
simulation_bp = Blueprint("simulation", __name__)
report_bp = Blueprint("report", __name__)
map_bp = Blueprint("map", __name__)
scene_bp = Blueprint("scene", __name__)
control_bp = Blueprint("control", __name__)
golden_cases_bp = Blueprint("golden_cases", __name__)

from . import control, golden_cases, graph, map_seed, report, scene_material, simulation  # noqa: E402,F401
