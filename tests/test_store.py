import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scholar_discovery import store

def rec(source_id,doi,title="Resilient API Integrations",year=2025):
    return {"source_id":source_id,"doi":doi,"title":title,"year":year}

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"data.sqlite3"

    def test_cross_source_same_doi_collapses_to_one_entity(self):
        a=store.ingest(self.db,"crossref",[rec("record-A","10.5555/SHARED")])
        b=store.ingest(self.db,"openalex",[rec("record-B","https://doi.org/10.5555/shared")])
        st=store.stats(self.db)
        self.assertEqual(a["new_doi_entities"],1)
        self.assertEqual(b["linked_existing"],1)
        self.assertEqual(st["entities"],1)
        self.assertEqual(st["observations"],2)
        self.assertEqual(len(store.search(self.db,"resilient")[0]["sources"]),2)

    def test_second_ingest_is_idempotent(self):
        row=rec("a","10.5555/demo")
        store.ingest(self.db,"crossref",[row])
        b=store.ingest(self.db,"crossref",[row])
        self.assertEqual(b["new_doi_entities"],0)
        self.assertEqual(b["updated_records"],0)
        self.assertEqual(b["unchanged_records"],1)
        self.assertEqual(store.stats(self.db)["observations"],1)

    def test_truly_new_doi_detected_after_old_database_exists(self):
        store.ingest(self.db,"crossref",[rec("a","10.5555/one")])
        result=store.ingest(self.db,"openalex",[rec("b","10.5555/two")])
        self.assertEqual(result["new_doi_entities"],1)
        self.assertEqual(store.stats(self.db)["confirmed_doi_entities"],2)

    def test_similar_title_without_identifier_not_auto_merged(self):
        store.ingest(self.db,"crossref",[rec("a",None,"Similar Title")])
        b=store.ingest(self.db,"openalex",[rec("b",None,"Similar Title")])
        self.assertEqual(b["provisional_entities"],1)
        self.assertEqual(b["new_doi_entities"],0)
        self.assertEqual(store.stats(self.db)["entities"],2)
        self.assertEqual(store.stats(self.db)["provisional_entities"],2)

    def test_conflicting_new_doi_does_not_overwrite_existing(self):
        store.ingest(self.db,"crossref",[rec("a","10.5555/one")])
        conflict=store.ingest(self.db,"crossref",[rec("a","10.5555/two")])
        self.assertEqual(conflict["conflicts"],1)
        self.assertEqual(store.stats(self.db)["identity_conflicts"],1)
        self.assertEqual(store.search(self.db,"resilient")[0]["doi"],"10.5555/one")

    def test_existing_provisional_can_receive_later_doi(self):
        store.ingest(self.db,"crossref",[rec("a",None)])
        update=store.ingest(self.db,"crossref",[rec("a","10.5555/one")])
        self.assertEqual(update["updated_records"],1)
        self.assertEqual(store.stats(self.db)["confirmed_doi_entities"],1)
        self.assertEqual(store.stats(self.db)["entities"],1)

    def test_doi_conflict_with_another_entity_is_flagged(self):
        store.ingest(self.db,"crossref",[rec("a","10.5555/one")])
        store.ingest(self.db,"openalex",[rec("b",None)])
        conflict=store.ingest(self.db,"openalex",[rec("b","10.5555/one")])
        self.assertEqual(conflict["conflicts"],1)
        self.assertEqual(store.stats(self.db)["entities"],2)

    def test_title_update_tracked_without_second_entity(self):
        store.ingest(self.db,"crossref",[rec("a","10.5555/one","First Title")])
        change=store.ingest(self.db,"crossref",[rec("a","10.5555/one","Corrected Title")])
        self.assertEqual(change["updated_records"],1)
        self.assertEqual(store.stats(self.db)["entities"],1)

    def test_input_validation_is_atomic(self):
        with self.assertRaises(ValueError):
            store.ingest(self.db,"crossref",[
                rec("a","10.5555/one"),
                {"source_id":"","title":"Bad"}
            ])
        self.assertFalse(self.db.exists())

    def test_query_limit_parameterized_and_readonly(self):
        store.ingest(self.db,"crossref",[rec("a","10.5555/one")])
        with self.assertRaises(ValueError):
            store.search(self.db,"resilient",51)
        self.assertEqual(store.search(self.db,"something' OR 1=1 --"),[])
        with store.db_connect(self.db,readonly=True) as conn:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("DELETE FROM entities")

    def test_invalid_input_limits(self):
        with self.assertRaises(ValueError):
            store.ingest(self.db,"BAD-SOURCE",[])
        with self.assertRaises(ValueError):
            store.ingest(self.db,"crossref",[{"source_id":"a","title":"hi","year":"2020"}])
        with self.assertRaises(FileNotFoundError):
            store.stats(self.db)

    def test_fixture_batch_counts(self):
        base=Path(__file__).resolve().parents[1]/"examples"
        a=json.loads((base/"crossref_sample.json").read_text())
        b=json.loads((base/"openalex_sample.json").read_text())
        r1=store.ingest(self.db,a["source"],a["records"])
        r2=store.ingest(self.db,b["source"],b["records"])
        self.assertEqual((r1["new_doi_entities"],r2["linked_existing"],r2["new_doi_entities"],r2["provisional_entities"]),(2,1,1,1))
        self.assertEqual(store.stats(self.db)["entities"],4)
        self.assertEqual(len(store.search(self.db,"OpenAlex")),1)

if __name__=="__main__":unittest.main()