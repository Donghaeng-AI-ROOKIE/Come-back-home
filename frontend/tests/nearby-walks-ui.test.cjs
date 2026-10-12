const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const ts=require('typescript');
const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');
const source=ts.transpileModule(fs.readFileSync('src/screens/CitizenHomeScreen.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
function screen(query){
  const buttons=[];let statsRefresh=0,walkRefresh=0;let refreshHome;
  const Box=({children})=>React.createElement('div',null,children);
  const Text=({children})=>React.createElement('span',null,children);
  const native={Platform:{OS:'web'},Alert:{alert(){}},View:Box,ScrollView:Box,Text,
    Pressable:props=>{buttons.push(props);return React.createElement('button',{'aria-label':props.accessibilityLabel},props.children)},
    RefreshControl:props=>{refreshHome=props.onRefresh;return null},
    ActivityIndicator:()=>React.createElement('span',null,'loading'),StyleSheet:{create:x=>x}};
  // ScrollView must render its RefreshControl so pull-to-refresh is exercised too.
  native.ScrollView=({children,refreshControl})=>React.createElement('div',null,refreshControl,children);
  const modules={react:React,'react-native':native,'react-native-safe-area-context':{SafeAreaView:Box},
    'expo-status-bar':{StatusBar:()=>null},'@react-navigation/native':{useNavigation:()=>({navigate(){}})},
    '../theme/tokens':{color:{brand:'green'},type:{}},
    '../hooks/queries':{useActiveWalk:()=>({}),useWalkStats:()=>({data:{},refetch(){statsRefresh++}}),
      useNearbyWalks:()=>({...query,refetch(){walkRefresh++}}),useStartWalk:()=>({mutate(){throw Error('unwanted walk start')}})},
    '../hooks/useMyLocation':{useMyLocation:()=>({status:'granted'}),isLocationSettled:()=>true,retryLocation(){}},
    'react-native-maps':{Polyline:()=>null},'../utils/walkFormat':{formatKm:()=> '0.00'}};
  const out={exports:{}};vm.runInNewContext(source,{exports:out.exports,require:name=>modules[name]??{__esModule:true,default:Box},module:out});
  const html=renderToStaticMarkup(React.createElement(out.exports.default));
  return {html,buttons,refresh(){refreshHome()},counts:()=>({statsRefresh,walkRefresh})};
}
test('upstream error is distinct from a successful empty search and is retryable',()=>{
  const s=screen({isError:true,data:undefined});assert.match(s.html,/정보를 불러오지 못했습니다/);
  assert.doesNotMatch(s.html,/장소를 찾지 못했습니다/);
  s.buttons.find(b=>b.accessibilityLabel==='산책 장소 다시 불러오기').onPress();
  assert.equal(s.counts().walkRefresh,1);
});
test('empty result offers a new search and pull refresh retries the places query too',()=>{
  const s=screen({isError:false,data:[]});assert.match(s.html,/반경 2km/);
  s.buttons.find(b=>b.accessibilityLabel==='주변 산책 장소 다시 검색').onPress();s.refresh();
  assert.deepEqual(s.counts(),{statsRefresh:1,walkRefresh:2});
});
test('available real routes still render their name and measured length',()=>{
  const s=screen({data:[{name:'실제 OSM 공원',lat:37.5,lng:126.9,path:[],kind:'park',route_km:1.2,distance_km:.3}]});
  assert.match(s.html,/실제 OSM 공원/);assert.match(s.html,/1.2/);assert.doesNotMatch(s.html,/다시 불러오기/);
});
