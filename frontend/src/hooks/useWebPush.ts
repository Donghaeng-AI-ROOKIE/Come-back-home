/** One root controller keeps push/location alive across citizen screens. */
import { createContext,useCallback,useContext,useEffect,useRef,useState } from 'react';
import { Platform } from 'react-native';
import { api } from '../api/config';
import { useMyLocation } from './useMyLocation';
import { useAuthStore } from '../store/authStore';
import { useEngagementLevel } from '../store/engagementStore';
import { cellOf } from '../utils/h3cell';
import { enteredTargets,EntryTarget } from '../utils/webPushEntry';
import { safeStorage } from '../store/safeStorage';
import { navigateWhenReady } from '../navigation/navigationRef';
export type WebPushStatus='unsupported'|'needs-install'|'disabled'|'idle'|'denied'|'subscribed'|'working';
function isIos(){return typeof navigator!=='undefined'&&/iPad|iPhone|iPod/.test(navigator.userAgent);}
function standalone(){return typeof window!=='undefined'&&Boolean(window.matchMedia?.('(display-mode: standalone)').matches||(navigator as Navigator&{standalone?:boolean}).standalone);}
function bytes(key:string):ArrayBuffer {
 const raw=atob((key+'='.repeat((4-key.length%4)%4)).replace(/-/g,'+').replace(/_/g,'/'));
 return Uint8Array.from(raw,c=>c.charCodeAt(0)).buffer;
}
const DEVICE_KEY='webpush-device-v1';
async function post<T>(path:string,body:unknown){return api<T>('/phase3/webpush/'+path,{method:'POST',body:JSON.stringify(body),headers:{'Content-Type':'application/json'}});}
export async function disableWebPush(){
 if(Platform.OS!=='web'||typeof navigator==='undefined'||!('serviceWorker' in navigator))return;
 const device=await safeStorage.getItem(DEVICE_KEY);
 const sub=await (await navigator.serviceWorker.getRegistration())?.pushManager.getSubscription();
 await sub?.unsubscribe();
 if(device){
   try{await api('/phase3/webpush/subscription',{method:'DELETE',body:JSON.stringify({device_id:device}),headers:{'Content-Type':'application/json'}});}
   finally{await safeStorage.removeItem(DEVICE_KEY);}
 }
}
export function useWebPushController(enabled:boolean){
 const [status,setStatus]=useState<WebPushStatus>('unsupported');
 const [error,setError]=useState('');const [message,setMessage]=useState('');
 const [device,setDevice]=useState<string|null>(null);
 const key=useRef('');const owner=useAuthStore(s=>s.userId);
 const location=useMyLocation(enabled);const level=useEngagementLevel();
 const live=useRef({location,device});live.current={location,device};
 const register=useCallback(async(sub:PushSubscription)=>{
   const loc=live.current.location;
   const fresh=loc.observedAt!=null&&Date.now()>=loc.observedAt&&Date.now()-loc.observedAt<60_000;
   const result=await post<{device_id:string}>('subscription',{subscription:sub.toJSON(),
     cell_res7:fresh?cellOf(loc.point):null,engagement:level});
   if(useAuthStore.getState().userId!==owner)return result.device_id;
   await safeStorage.setItem(DEVICE_KEY,result.device_id);setDevice(result.device_id);return result.device_id;
 },[level,owner]);
 useEffect(()=>{
   setDevice(null);key.current='';
   if(!enabled||Platform.OS!=='web'||typeof window==='undefined')return;
   if(isIos()&&!standalone()){setStatus('needs-install');return;}
   if(!('serviceWorker' in navigator)||!('PushManager' in window)||!('Notification' in window)){setStatus('unsupported');return;}
   if(Notification.permission==='denied'){setStatus('denied');return;}
   let cancelled=false;setStatus('working');
   void(async()=>{
     try{
       const conf=await api<{key:string;enabled:boolean}>('/phase3/webpush/public-key');
       if(cancelled)return;
       if(!conf.enabled||!conf.key){setStatus('disabled');return;}
       key.current=conf.key;
       const reg=await navigator.serviceWorker.register('/sw.js');await navigator.serviceWorker.ready;
       const sub=await reg.pushManager.getSubscription();
       if(cancelled)return;
       if(sub){await register(sub);if(!cancelled)setStatus('subscribed');}
       else setStatus('idle');
     }catch{if(!cancelled){setStatus('idle');setError('알림 연결을 확인하지 못했어요. 잠시 후 다시 열어 주세요.');}}
   })();
   return()=>{cancelled=true;};
 },[enabled,owner,register]);
 const enable=useCallback(async()=>{
   if(!key.current){setError('알림 서버에 연결한 뒤 다시 시도해 주세요.');return;}
   // iOS requires a direct tap gesture, before any network await.
   const requested=Notification.requestPermission();setStatus('working');setError('');
   try{
     if(await requested!=='granted'){setStatus('denied');return;}
     const reg=await navigator.serviceWorker.ready;
     const sub=(await reg.pushManager.getSubscription())??await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:bytes(key.current)});
     await register(sub);setStatus('subscribed');
   }catch{setStatus('idle');setError('알림 연결에 실패했어요. 다시 눌러 주세요.');}
 },[register]);
 useEffect(()=>{
   if(!enabled||status!=='subscribed'||!device)return;
   let cancelled=false,busy=false;
   const check=async()=>{
     if(cancelled||busy||document.visibilityState!=='visible')return;
     busy=true;
     try{
       const loc=live.current.location;
       const fresh=loc.status==='granted'&&loc.observedAt!=null&&Date.now()>=loc.observedAt&&Date.now()-loc.observedAt<=60_000;
       const result=await post<{targets:EntryTarget[]}>('location',{device_id:device,cell_res7:fresh?cellOf(loc.point):null});
       if(cancelled)return;
       const current=live.current.location;
       if(!fresh || cellOf(current.point)!==cellOf(loc.point))return;
       for(const caseId of enteredTargets(current.point,current.accuracyM,current.observedAt,result.targets)){

         const sent=await post<{status:string}>('enter',{device_id:device,case_id:caseId});
         if(cancelled)return;

         if(sent.status==='accepted')setMessage('주변 실종자 알림 대상 구역에 들어왔어요. 알림을 확인해 주세요.');
         else if(sent.status==='failed')setError('구역 진입을 확인했지만 푸시를 보내지 못했어요. 긴급 알림 탭을 확인해 주세요.');
       }
     }catch{if(!cancelled)setError('알림 연결이 지연돼요. 다음 위치 확인 때 다시 연결합니다.');}
     finally{busy=false;}
   };
   void check();const id=setInterval(()=>void check(),15_000);
   document.addEventListener('visibilitychange',check);
   return()=>{cancelled=true;clearInterval(id);document.removeEventListener('visibilitychange',check);};
 },[enabled,status,device]);
 useEffect(()=>{
   if(!enabled||Platform.OS!=='web'||!('serviceWorker' in navigator))return;
   const go=(id:unknown)=>typeof id==='string'&&/^[\w-]{1,80}$/.test(id)&&navigateWhenReady('AlertDetail',{caseId:id});
   const receive=(event:MessageEvent)=>{if(event.data?.type==='CBH_OPEN_CASE')go(event.data.case_id);};
   navigator.serviceWorker.addEventListener('message',receive);
   const rawId=new URL(window.location.href).searchParams.get('case_id');
   const id=rawId&&/^[\w-]{1,80}$/.test(rawId)?rawId:null;
   const openPending=()=>{if(id&&go(id)){const url=new URL(window.location.href);url.searchParams.delete('case_id');history.replaceState(null,'',url.toString());return true;}return false;};
   const timer=!openPending()&&id?setInterval(()=>{if(openPending())clearInterval(timer as ReturnType<typeof setInterval>);},500):null;
   return()=>{if(timer)clearInterval(timer);navigator.serviceWorker.removeEventListener('message',receive);};
 },[enabled]);
 const test=useCallback(async()=>{
   if(!device)return;
   setError('');try{
     const res=await post<{status:string}>('test',{device_id:device});
     setMessage(res.status==='accepted'?'시험 알림을 요청했어요. 실제 알림이 도착하는지 확인해 주세요.':
       res.status==='cooldown'?'1분 뒤 다시 시험할 수 있어요.':'시험 알림을 보내지 못했어요.');
   }catch{setError('시험 알림 요청이 실패했어요.');}
 },[device]);
 const disable=useCallback(async()=>{
   try{await disableWebPush();setDevice(null);setStatus('idle');setMessage('알림을 껐어요.');}
   catch{setDevice(null);setStatus('idle');setError('기기 알림을 껐어요. 서버 정리는 연결 후 다시 확인해 주세요.');}
 },[]);
 return {status,error,message,enable,test,disable,isIos:isIos(),isStandalone:standalone(),location};
}
type State=ReturnType<typeof useWebPushController>;
export const WebPushContext=createContext<State|null>(null);
export function useWebPush(){const value=useContext(WebPushContext);if(!value)throw new Error('Web push controller missing');return value;}
