import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from scholar_discovery import store,http_api

class HttpTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db=str(Path(tmp.name)/"data.sqlite")
        store.ingest(self.db,"crossref",[{"source_id":"one","doi":"10.5555/demo",
                 "title":"Public Metadata","year":2026}])
        self.server=ThreadingHTTPServer(("127.0.0.1",0),
                   http_api.make_handler(self.db,"test-secret-value-long"))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port=self.server.server_address[1]

    def request(self,path,token="",method="GET"):
        h={"Authorization":"Bearer "+token} if token else {}
        req=Request("http://127.0.0.1:"+str(self.port)+path,headers=h,method=method)
        try:
            with urlopen(req,timeout=3) as response:
                return response.status,json.load(response)
        except HTTPError as e:
            return e.code,json.loads(e.read())

    def test_requires_bearer_token(self):
        code,_=self.request("/v1/stats")
        self.assertEqual(code,401)
        code,_=self.request("/v1/stats","bad-token")
        self.assertEqual(code,401)

    def test_search_is_readonly_and_bounded(self):
        code,body=self.request("/v1/search?q=public","test-secret-value-long")
        self.assertEqual(code,200)
        self.assertEqual(body["count"],1)
        code,body=self.request("/v1/search?q=public&limit=999","test-secret-value-long")
        self.assertEqual(code,400)
        code,body=self.request("/v1/search?q=public","test-secret-value-long","POST")
        self.assertEqual(code,405)
        self.assertEqual(store.stats(self.db)["entities"],1)

if __name__=="__main__":unittest.main()
