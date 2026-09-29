const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const path=require('node:path');
const root=path.resolve(process.argv[2] || process.cwd());
const ts=require(path.join(root,'frontend/node_modules/typescript'));
const source=fs.readFileSync(path.join(root,'frontend/src/features/configuration/projects/drafts/usePersistentDraft.ts'),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const slots=[];let cursor=0;
const react={useRef(value){const i=cursor++;return slots[i]??=( {current:value} );},useState(value){const i=cursor++;if(!(i in slots))slots[i]=value;return [slots[i],v=>{slots[i]=typeof v==='function'?v(slots[i]):v;}];},useEffect(){}};
class ApiError extends Error {constructor(message,status){super(message);this.status=status;}}
const clone=x=>structuredClone(x), receipts=new Map();
const initial={note:'A'};let workspace={id:'draft',revision:1,base_revision:0,configuration:initial,checked:{configuration:initial}};
let saved, failRead=true;const calls=[];
async function post(path,request){
 calls.push({path,request:clone(request)});
 if(receipts.has(request.operation_id))return clone(receipts.get(request.operation_id));
 assert.equal(request.expected_revision,workspace.revision);
 let result;
 if(path==='/list-tools/list_check')result={revision:++workspace.revision,check_fingerprint:'checked'};
 else if(path==='/list-tools/list_save'){saved={revision:1,configuration:clone(workspace.configuration)};workspace.revision++;workspace.base_revision=1;result={project_revision:1};}
 else if(path==='/work-drafts/draft/edit'){workspace.configuration={note:'B'};workspace.checked={configuration:workspace.configuration};result={revision:++workspace.revision,configuration_patch:{note:'B'},checked_patch:{}};}
 else throw new Error(path);
 receipts.set(request.operation_id,clone(result));return result;
}
async function api(path){if(path==='/work-drafts/draft')return clone(workspace);if(path==='/configuration/projects/p'){if(failRead){failRead=false;throw new Error('injected failure after successful save');}return clone(saved);}throw new Error(path);}
const modules={react,'react-router-dom':{useBlocker:()=>({state:'unblocked'}),useSearchParams:()=>[{},()=>{}]},antd:{App:{useApp:()=>({modal:{}})}},'../../../../shared/api':{api,ApiError},'./operations':{configurationOperations:()=>{throw new Error('unused');}},'./transport':{post,writeRequest:(w,operations)=>({expected_revision:w.revision,operation_id:crypto.randomUUID(),operations}),mergeDelta:(w,d)=>({...w,revision:d.revision,configuration:{...w.configuration,...d.configuration_patch},checked:{configuration:{...w.configuration,...d.configuration_patch}}})}};
const exportsObject={};vm.runInNewContext(js,{exports:exportsObject,require:name=>{if(!(name in modules))throw new Error(name);return modules[name];},crypto:globalThis.crypto,URLSearchParams});
const options={projectId:'p',saved:{revision:0,configuration:initial},configuration:initial,initialWorkspace:clone(workspace),accept(){},acceptOperation(){}};
const render=()=>{cursor=0;return exportsObject.usePersistentDraft(options);};
(async()=>{
 let hook=render();await assert.rejects(hook.save(),/injected/);
 const checked=await hook.execute([{action:'device_patch',note:'B'}]);options.configuration=checked.configuration;hook=render();
 const result=await hook.save();
 console.log(JSON.stringify({currentDraft:workspace.configuration,saveReturned:result.configuration,saveRequests:calls.filter(x=>x.path==='/list-tools/list_save'),projectRevision:result.revision},null,2));
 assert.equal(result.configuration.note,'B','A new edit must not be reported as saved using the previous save receipt');
})().catch(error=>{console.error(error.message);process.exitCode=1;});
