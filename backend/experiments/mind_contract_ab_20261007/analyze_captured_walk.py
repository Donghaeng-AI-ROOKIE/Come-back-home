"""Inspect saved traces and export transparent plots; no calls or new simulation."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import h3
from shapely import wkt


def read(p): return json.loads(Path(p).read_text())
def save(p,x): Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n")


def tv(a,b):
    return .5*sum(abs(a.get(k,0)-b.get(k,0)) for k in set(a)|set(b))


def inspect_trace(data, scene, facilities):
    import math
    rules={r['id']:r for r in data['policy']['rules']}
    checked=Counter(); violations=[]
    start_point=(facilities['market'][0] if scene=='place_noise' else None)
    for index,trace in data['traces'].items():
        prev={'minute':0,'distance_m':0,'continuous_walk':0,**(start_point or {})}
        rest_block=None; stationary_distance=0
        for point in trace:
            end=point['minute']; start=prev['minute']; mid=(start+end)/2
            rule=rules.get(point['rule_id'])
            personal_rest=rule and point['mode']=='rest'
            if rest_block is not None and not personal_rest:
                checked['complete_personal_rests']+=1
                if abs(rest_block['end']-rest_block['start']-5)>1e-4:
                    violations.append({'particle':index,'reason':'complete personal rest duration differs from5',**rest_block})
                rest_block=None
            if personal_rest:
                if rest_block is None:
                    rest_block={'start':start,'end':end}
                    checked['personal_rest_starts']+=1
                    if prev['continuous_walk']<6-1e-4 and prev['distance_m']-stationary_distance<280-1e-4:
                        violations.append({'particle':index,'reason':'personal rest before either source threshold','minute':start})
                else: rest_block['end']=end
            if rule and point['mode']=='wait':
                checked['personal_wait_segments']+=1
                if scene!='wait_release' or not (40-1e-4<=mid<90+1e-4 or 210-1e-4<=mid<230+1e-4):
                    violations.append({'particle':index,'reason':'personal waiting outside source condition window','start':start,'end':end})
            if rule and point['mode']=='avoid':
                checked['personal_avoid_segments']+=1
                if scene!='place_noise' or not (0<=mid<20+1e-4 or 80-1e-4<=mid<130+1e-4):
                    violations.append({'particle':index,'reason':'avoidance outside noisy observation window','minute':mid})
                target=facilities['market'][0]
                if 'lat' not in prev: raise ValueError('missing start position for avoidance audit')
                distance=((prev['lat']-target['lat'])*111000)**2+((prev['lng']-target['lng'])*111000*math.cos(math.radians(prev['lat'])))**2
                if math.sqrt(distance)>60.5: # geometry-check tolerance, not a changed engine rule
                    violations.append({'particle':index,'reason':'avoidance starts outside named place scope','distance_m':math.sqrt(distance)})
            if point['mode'] in ('wait','rest'): stationary_distance=point['distance_m']
            prev=point
        if rest_block is not None:
            checked['right_censored_rest_blocks']+=1
    return {'trace_particles':len(data['traces']),'checked':dict(checked),'violations':violations,
        'limit':'first five fixed particles only; not all500, no clinical accuracy'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--walk',type=Path,required=True);p.add_argument('--map',type=Path,required=True)
    a=p.parse_args();summary=read(a.walk/'summary.json')
    if read(a.walk/'status.json')['state']!='offline_walk_complete': raise SystemExit('walk incomplete')
    plots={};audit=[]
    for scene in ('rest_cycle','wait_release','place_noise'):
        plots[scene]={}
        reference=read(a.walk/scene/'author_reference.json')
        for name in ('empty_policy','d4_rep1','d12_rep1','d12_rep2'):
            data=read(a.walk/scene/(name+'.json'))
            stamps=data['timeline']; changes=[{'from_minute':x['minute'],'to_minute':y['minute'],
                'total_variation':tv(x['distribution']['cells'],y['distribution']['cells'])} for x,y in zip(stamps,stamps[1:])]
            same_final={k:data['timeline'][-1]['metrics'][k]==reference['timeline'][-1]['metrics'][k] for k in
                ('mean_path_km','mean_wait_minutes','mean_personal_rest_minutes','avoid_walkers','avoid_targets','unresolved_mass')}
            row={'scene':scene,'candidate':name,'time_changes':changes,'matches_reference_final_components':same_final,
                 'distribution_tv_vs_reference':tv(stamps[-1]['distribution']['cells'],reference['timeline'][-1]['distribution']['cells'])}
            row['trace_check']=inspect_trace(data,scene,read(a.walk/'manifest.json')['facilities'])
            audit.append(row)
            for t in stamps:
                t['points']=[{'lat':h3.cell_to_latlng(cell)[0],'lng':h3.cell_to_latlng(cell)[1],'p':prob}
                    for cell,prob in t['distribution']['cells'].items()]
            plots[scene][name]={'timeline':stamps,'trace0':data['traces']['0']}
    ns={'g':'http://graphml.graphdrawing.org/xmlns'}
    tree=ET.parse(a.map); keys={x.attrib['id']:x.attrib.get('attr.name') for x in tree.getroot().findall('g:key',ns)}
    nodes={};roads=[]
    for n in tree.findall('.//g:node',ns):
        d={keys[v.attrib['key']]:v.text for v in n.findall('g:data',ns)}
        nodes[n.attrib['id']]=[float(d['x']),float(d['y'])]
    for e in tree.findall('.//g:edge',ns):
        vals={keys[v.attrib['key']]:v.text for v in e.findall('g:data',ns)}
        if vals.get('geometry'): coords=list(wkt.loads(vals['geometry']).coords)
        else: coords=[nodes[e.attrib['source']],nodes[e.attrib['target']]]
        roads.append(coords)
    save(a.walk/'behavior_audit.json',{'scope':'saved executable effects against author reference, one synthetic person',
        'rows':audit,'clinical_accuracy':False,'release_qualified':False})
    save(a.walk/'plot_data.json',{'plots':plots,'roads':roads,'manifest':read(a.walk/'manifest.json')})
    print(json.dumps({'rows':len(audit),'time_maps_all_changed':all(x['total_variation']>0 for r in audit for x in r['time_changes']),
        'trace_violations':sum(len(r.get('trace_check',{}).get('violations',[])) for r in audit)},ensure_ascii=False))


if __name__=='__main__':main()
