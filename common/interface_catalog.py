"""Developer-confirmed interface lifecycle for the current 4.39.7 code line.

This is a traceability inventory, not a runtime alias map: replacements can have
different request shapes or business effects and must be tested explicitly.
"""

RETIRED_METHODS = {
    "device.devUpdate": {
        "change": "renamed", "replacement": "device.devUpdate2", "commit": "a0cbc09",
        "reason": "4.39 Dameng adaptation removed the old processor; devUpdate2 includes memLoad",
    },
    "device.updateService": {
        "change": "removed", "replacement": None, "commit": "3c58815",
        "reason": "Service status update removed; registerService/serviceUnregister are not equivalent replacements",
    },
    "room.deleteRoomRouteInfo": {
        "change": "merged", "replacement": "room.delRoomRoute", "commit": "3c58815",
        "reason": "Route deletion uses roomId/svrAppId/svrNodeId; roomId=0 selects scoped bulk deletion",
    },
    "room.getRoomDeptList": {
        "change": "renamed", "replacement": "room.getRoomDeptList2", "commit": "a0cbc09",
        "reason": "Response uses getRoomDeptList2; room department lookup falls back to t_roomruninfo",
    },
}
