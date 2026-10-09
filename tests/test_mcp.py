import json
import tempfile
import unittest
from pathlib import Path
from scholar_discovery import mcp,store

class MCPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"mcp.sqlite3"
        store.ingest(self.db,"crossref",[{
            "source_id":"work-1","doi":"10.5555/unique","title":"Unique Publication",
            "year":2026}])
    def msg(self,method,params=None):
        d={"jsonrpc":"2.0","id":7,"method":method}
        if params is not None:d["params"]=params
        return mcp.handle(d,self.db)
    def test_initialization(self):
        r=self.msg("initialize",{"protocolVersion":"2025-06-18","clientInfo":{"name":"test","version":"0.1"},"capabilities":{}})
        self.assertEqual(r["result"]["serverInfo"]["name"],"scholar-discovery-readonly")
    def test_list_only_readonly_tools(self):
        r=self.msg("tools/list")
        self.assertEqual([t["name"] for t in r["result"]["tools"]],["search_publications","discovery_stats"])
    def test_search_tool(self):
        r=self.msg("tools/call",{"name":"search_publications","arguments":{"query":"unique","limit":5}})
        self.assertEqual(len(json.loads(r["result"]["content"][0]["text"])),1)
    def test_stats_tool(self):
        r=self.msg("tools/call",{"name":"discovery_stats","arguments":{}})
        self.assertEqual(json.loads(r["result"]["content"][0]["text"])["entities"],1)
    def test_refuses_write_or_sql_tool(self):
        r=self.msg("tools/call",{"name":"execute_sql","arguments":{"sql":"DROP TABLE entities"}})
        self.assertEqual(r["error"]["code"],-32602)
        self.assertEqual(store.stats(self.db)["entities"],1)
    def test_bounded_tool_results(self):
        r=self.msg("tools/call",{"name":"search_publications","arguments":{"query":"unique","limit":100000}})
        self.assertTrue(r["result"]["isError"])
    def test_rejects_extra_properties(self):
        r=self.msg("tools/call",{"name":"search_publications","arguments":{"query":"unique","write":True}})
        self.assertTrue(r["result"]["isError"])
    def test_unknown_method_and_notification(self):
        self.assertEqual(self.msg("weird")["error"]["code"],-32601)
        self.assertIsNone(mcp.handle({"jsonrpc":"2.0","method":"notifications/initialized"},self.db))

if __name__=="__main__":unittest.main()
