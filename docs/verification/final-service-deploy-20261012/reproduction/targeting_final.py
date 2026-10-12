import socket,json
def blocked(*a,**k):raise RuntimeError('network blocked')
socket.socket.connect=blocked;socket.create_connection=blocked
from app import storage
from app.main import app
from app.phase3 import alerts,devices,webpush_entry
from app.schemas.device import Engagement,Platform
from fastapi.testclient import TestClient
import h3
c=storage.cases.get('deploy-final-e09-c');assert c and c.synthetic_test
c.synthetic_test=False;storage.cases.save(c.id,c) # isolated preflight volume only
chosen=alerts.select_alert_cells(c.current_poa);target=alerts.target_parent_cells(chosen)
outside=set(h3.grid_disk(h3.latlng_to_cell(c.lkp.lat,c.lkp.lng,9),8))-target
test_cells=target|set(sorted(outside)[:20]);client=TestClient(app);captured=[];checks=0
for cell in sorted(test_cells):
 rows=client.get('/phase3/alerts',params={'target_cell':cell}).json()
 assert any(r['case_id']==c.id for r in rows)==(cell in target)
 for level in Engagement:
  d=devices.register('deploy-'+cell+'-'+level.value,Platform.android,cell,level)
  assert any(r['case_id']==c.id for r in webpush_entry.targets(cell,d))==(cell in target)
  checks+=1
def stub(tokens,**kw):
 assert set(kw['data']['target_cells'])==target and kw['data']['target_res']==9
 captured.extend(tokens)
 return {'sent':len(tokens),'failed':0,'sent_tokens':tokens,'failed_tokens':[],'stub':True}
alerts.push.send=stub
result=alerts.send_alerts(c.id,chosen,'synthetic',poa=c.current_poa)
expected={'deploy-'+cell+'-'+level.value for cell in target for level in Engagement}
assert set(captured)==expected and result['sent']==len(expected)
assert client.get('/phase3/targeting-policy').json()['max_area_km2']==5.8
c.synthetic_test=True;storage.cases.save(c.id,c)
print(json.dumps({'passed':True,'synthetic_recipient_checks':checks,'selected_cells':len(target),'outside_cells':len(test_cells-target),'stub_recipients':len(expected),'app_web_fanout_mismatches':0,'network':'none','real_push':0,'model_calls':0,'scope':'new live image on separate preflight data volume'}))
