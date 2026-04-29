"""Central registry for app modules."""

from typing import List

from .admin import get_module as get_admin_module
from .base import AppModule
from .bug_tracker import get_module as get_bug_tracker_module
from .checklist_item_types import get_module as get_checklist_item_types_module
from .checklists import get_module as get_checklists_module
from .gear import get_module as get_gear_module
from .planned_hikes import get_module as get_planned_hikes_module
from .stats import get_module as get_stats_module
from .trails import get_module as get_trails_module
from .welcome import get_module as get_welcome_module


def load_modules() -> List[AppModule]:
    """
    Return all available modules.

    Add/remove module imports here to control app capabilities.
    """
    return [
        get_welcome_module(),
        get_bug_tracker_module(),
        get_admin_module(),
        get_checklist_item_types_module(),
        get_checklists_module(),
        get_trails_module(),
        get_planned_hikes_module(),
        get_gear_module(),
        get_stats_module(),
    ]
