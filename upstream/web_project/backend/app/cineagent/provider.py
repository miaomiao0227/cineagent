"""Official-only DeepSeek client with persistent, conservative trial reservations.
No credentials/prompts/responses are written to the accounting ledger.
Unknown/failed request usage retains its entire reservation (fail closed).
"""
import json, os, time, uuid, urllib.request, urllib.error
from pathlib import Path
from contextlib import contextmanager

class BudgetExceeded(RuntimeError):pass
class ProviderError(RuntimeError):pass

@contextmanager
def file_lock(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,'a+b') as f:
        if f.tell()==0:f.write(b'0');f.flush()
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class DeepSeekTrial:
    def __init__(self,config,ledger,approved_campaign=False,budget_window=None,parent_request_id=None):
        self.config=Path(config);self.ledger=Path(ledger);self.approved_campaign=approved_campaign;self.budget_window=budget_window;self.parent_request_id=parent_request_id
    def _read(self):
        return json.loads(self.ledger.read_text(encoding='utf-8')) if self.ledger.exists() else {'version':'trial-v1','attempts':[]}
    def _write(self,data):
        self.ledger.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.ledger.with_suffix('.tmp')
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,self.ledger)
    def chat(self,messages,tools=None,max_tokens=512,trial_authorized=False):
        cfg=json.loads(self.config.read_text(encoding='utf-8-sig'))
        if not trial_authorized and not cfg.get('enabled',False):raise ProviderError('provider_disabled')
        if cfg.get('base_url')!='https://api.deepseek.com' or cfg.get('model')!='deepseek-flash':raise ProviderError('unapproved_provider_or_model')
        if not 1<=max_tokens<=1024:raise ValueError('output_limit_out_of_range')
        payload={'model':'deepseek-flash','messages':messages,'max_tokens':max_tokens,'thinking':{'type':'disabled'},'temperature':0,'stream':False}
        if tools:payload['tools']=tools;payload['tool_choice']='auto'
        raw=json.dumps(payload,ensure_ascii=False).encode('utf-8')
        # UTF-8 bytes plus framing allowance exceed normal tokenization for these bounded text prompts.
        reserve_in=len(raw)+128*(len(messages)+1);reserve_out=max_tokens
        rid=str(uuid.uuid4());limits=cfg['approved_trial']
        if self.approved_campaign:
            if self.ledger.name!='DEEPSEEK_NATURAL_V2_LEDGER.json':raise ProviderError('invalid_campaign_ledger')
            limits={'max_requests_including_retries':240,'max_input_tokens':600000,'max_output_tokens':120000,'budget_usd':.50}
        caps=(240,600000,120000,.50) if self.approved_campaign else (30,150000,30000,.10)
        with file_lock(self.ledger.with_suffix('.lock')):
            log=self._read();attempts=log['attempts']
            if self.budget_window:
                w=self.budget_window;subset=attempts[w['start_attempt']:]
                if len(subset)>=w['max_new_attempts']:raise BudgetExceeded('batch_request_limit')
                window_cost=sum(x['accounted_input_tokens']*.30/1e6+x['accounted_output_tokens']*1.20/1e6 for x in subset)
                if window_cost+reserve_in*.30/1e6+reserve_out*1.20/1e6>w['max_new_cost_usd']:raise BudgetExceeded('batch_cost_limit')
            total_in=sum(x['accounted_input_tokens'] for x in attempts);total_out=sum(x['accounted_output_tokens'] for x in attempts)
            if len(attempts)>=min(caps[0],limits['max_requests_including_retries']):raise BudgetExceeded('request_limit')
            if total_in+reserve_in>min(caps[1],limits['max_input_tokens']):raise BudgetExceeded('input_limit')
            if total_out+reserve_out>min(caps[2],limits['max_output_tokens']):raise BudgetExceeded('output_limit')
            cost=(total_in+reserve_in)*.30/1e6+(total_out+reserve_out)*1.20/1e6
            if cost>min(caps[3],limits['budget_usd']):raise BudgetExceeded('cost_limit')
            entry={'request_id':rid,'status':'reserved','accounted_input_tokens':reserve_in,'accounted_output_tokens':reserve_out,'created_at_unix':time.time()};entry['parent_request_id']=self.parent_request_id;attempts.append(entry);self._write(log)
        started=time.monotonic();result=None;status='failed_unknown_usage';error=None
        try:
            req=urllib.request.Request('https://api.deepseek.com/chat/completions',data=raw,headers={'Authorization':'Bearer '+cfg['api_key'],'Content-Type':'application/json'},method='POST')
            with urllib.request.build_opener(NoRedirect()).open(req,timeout=8) as response:
                body=response.read(1024*1024+1)
                if len(body)>1024*1024:raise ProviderError('response_too_large')
                result=json.loads(body)
            usage=result.get('usage',{});pi=usage.get('prompt_tokens');po=usage.get('completion_tokens')
            if not isinstance(pi,int) or not isinstance(po,int) or pi<0 or po<0:raise ProviderError('invalid_usage')
            if pi>reserve_in or po>reserve_out:raise ProviderError('usage_exceeded_reservation')
            status='ok'
        except urllib.error.HTTPError as exc:error='http_'+str(exc.code)
        except Exception as exc:error=type(exc).__name__
        finally:
            with file_lock(self.ledger.with_suffix('.lock')):
                log=self._read();entry=next(x for x in log['attempts'] if x['request_id']==rid)
                entry.update(status=status,elapsed_ms=round((time.monotonic()-started)*1000,2),error_type=error)
                if status=='ok':entry.update(accounted_input_tokens=pi,accounted_output_tokens=po,model_returned=result.get('model'),provider_request_id=result.get('id'))
                self._write(log)
        if status!='ok':raise ProviderError(error or 'provider_failed')
        return result,rid

