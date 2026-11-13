"""Confirmed legacy deletion removes directory entries and retains file records."""
import uuid

import allure
import pytest

from common.executor import attach
from common.scenarios import same_rows


pytestmark = pytest.mark.integration


@pytest.mark.parametrize("depth", [1, 3], ids=["direct_files", "nested_files"])
def test_delete_directory_entries_preserves_file_records(workflow, depth):
    allure.dynamic.label("issue_id", "DESIGN-DEL-DIR-DIRECTORY-ONLY")
    allure.dynamic.label("test_group", "behavior_baseline")
    with workflow("delete_directory_entries_preserve_files_depth_%d" % depth, method="delDir",
                  requires=["write", "database", "room", "file"]) as s:
        env = s.context["env"]
        prefix = "autotest_tree_" + uuid.uuid4().hex[:16] + "_"
        room_id = env["room_id"]
        sql = "SELECT RoomID,DocID,ParentID,DocName,DocType FROM t_roomdocslist WHERE DocID LIKE %s ORDER BY DocID"
        assert not s.rows(sql, [prefix + "%"])
        prepared = {}

        def verify_cleanup():
            assert not s.rows(sql, [prefix + "%"]), "Tree fixture left records behind"

        # Registered first, this final assertion runs after all API deletions.
        s.add_cleanup("all tree records absent across rooms", verify_cleanup)

        def create(label, parent, doc_type):
            doc_id = prefix + label
            prepared[doc_id] = {"RoomID": str(room_id), "DocID": doc_id, "ParentID": parent,
                                "DocName": label, "DocType": str(doc_type)}

            def cleanup():
                s.api("file", "delFile", {"roomId": room_id, "docId": doc_id})
                assert not s.rows("SELECT DocID FROM t_roomdocslist WHERE DocID=%s", [doc_id])

            # Register before calling addFile in case a response fails after insertion.
            s.add_cleanup(doc_id, cleanup)
            s.api("file", "addFile", {
                "roomId": room_id, "docId": doc_id, "parentId": parent,
                "docName": label, "docType": doc_type, "fileName": label,
                "fileExt": "" if doc_type == 0 else "txt", "fileSize": 1,
                "checkCode": 1, "creatorId": env["user_id"], "fileWidth": 0,
                "fileHeight": 0, "subFileCount": 0, "fileUrl": "autotest.txt",
                "fileServiceId": env["primary"]["services"]["FMFileSrv"]["id"]})
            return doc_id

        sibling = create("unrelated_dir", "", 0)
        outside = create("unrelated_file", sibling, 2)
        controls = {sibling, outside}
        root = create("root", "", 0)
        parent = root
        tree_ids = {root}
        for level in range(depth):
            if level:
                parent = create("dir_%d" % level, parent, 0)
                tree_ids.add(parent)
            for doc_type in [1, 2, 3]:
                tree_ids.add(create("file_%d_%d" % (level, doc_type), parent, doc_type))

        before = s.rows(sql, [prefix + "%"])
        assert same_rows(before, list(prepared.values())), "Directory/file fixture did not persist the exact requested tree"
        expected_controls = [row for row in before if row["DocID"] in controls]
        expected_files = [row for row in before if row["DocID"] in tree_ids and str(row["DocType"]) != "0"]
        expected_directory_ids = {row["DocID"] for row in before if row["DocID"] in tree_ids and str(row["DocType"]) == "0"}
        assert len(expected_directory_ids) == depth and len(expected_files) == depth * 3
        result = s.runtime.call("file", "delDir", {"roomId": room_id, "docId": root})
        after = s.rows(sql, [prefix + "%"])
        remaining = [row for row in after if row["DocID"] in tree_ids]
        actual_controls = [row for row in after if row["DocID"] in controls]
        remaining_directories = [row for row in after if row["DocID"] in expected_directory_ids]
        attach("Confirmed directory-only deletion verification", {
            "depth": depth, "tree_ids": sorted(tree_ids), "before": before,
            "after": after, "retained_file_records": remaining, "expected_retained_file_records": expected_files,
            "remaining_directory_records": remaining_directories,
            "unrelated_records_unchanged": same_rows(actual_controls, expected_controls),
            "scope": "Developer retained existing directory-only deletion; complete file-tree cleanup is outside this API assertion",
            "response": result.evidence()})
        errors = []
        if result.invoke_code != 0 or result.response_code != 0:
            errors.append("Valid nonempty directory delete failed: %s/%s" %
                          (result.invoke_code, result.response_code))
        if remaining_directories:
            errors.append("Directory-only delete left directory records: %s" % [row["DocID"] for row in remaining_directories])
        if not same_rows(after, expected_files + expected_controls):
            errors.append("Directory-only delete must retain every original file record unchanged and remove only the selected directory entries")
        if not same_rows(actual_controls, expected_controls):
            errors.append("Directory delete changed unrelated sibling records")
        assert not errors, "; ".join(errors)
