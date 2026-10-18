"""Local-only credential dialog; no HTTP requests and no credential logging."""
import json
import os
from pathlib import Path
import tempfile

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'configs'/'local-secrets'/'deepseek.json'

def save_key(key, dest=DEST):
    key=key.strip()
    if not key or len(key)<16 or any(c.isspace() for c in key):
        raise ValueError('请输入完整 API key，不能含空格或换行。')
    payload={'provider':'deepseek','base_url':'https://api.deepseek.com','model':'deepseek-flash','api_key':key,
             'enabled':False,'approved_trial':{'max_requests_including_retries':30,'max_input_tokens':150000,'max_output_tokens':30000,'budget_usd':0.10}}
    dest.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.credential-',dir=dest.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            json.dump(payload,out,ensure_ascii=False);out.flush();os.fsync(out.fileno())
        os.replace(tmp,dest)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def main():
    import tkinter as tk
    from tkinter import messagebox
    win=tk.Tk();win.title('CineAgent · DeepSeek 本机配置');win.geometry('640x340');win.resizable(False,False)
    frame=tk.Frame(win,padx=24,pady=20);frame.pack(fill='both',expand=True)
    tk.Label(frame,text='DeepSeek 官方 API key',font=('Microsoft YaHei UI',14,'bold')).pack(anchor='w')
    tk.Label(frame,text='模型：deepseek-flash    接口：https://api.deepseek.com',anchor='w').pack(anchor='w',pady=(12,8))
    value=tk.StringVar();entry=tk.Entry(frame,textvariable=value,show='●',width=65,font=('Consolas',11));entry.pack(fill='x');entry.focus_set()
    tk.Label(frame,text='仅保存在本机 D 盘项目配置；不调用 API、不测试余额。\n保存后默认保持禁用，由受预算限制的接入流程启用。\n文件为本机明文凭据，请勿分享 local-secrets 文件夹。',justify='left',fg='#555555').pack(anchor='w',pady=14)
    status=tk.StringVar(value='已存在本机配置；重新保存将替换密钥。' if DEST.exists() else '尚未配置。')
    tk.Label(frame,textvariable=status,fg='#246449').pack(anchor='w')
    def save():
        try:save_key(value.get())
        except ValueError as exc:messagebox.showerror('未保存',str(exc));return
        except Exception:messagebox.showerror('未保存','本机文件写入失败，请检查目录权限。');return
        value.set('');status.set('已保存，输入框已清空。尚未发起任何 API 调用。')
        messagebox.showinfo('已保存','API key 已保存到本机配置。你可以关闭此窗口。')
    tk.Button(frame,text='保存到本机',command=save,width=20).pack(anchor='e',pady=10)
    win.mainloop()

if __name__=='__main__':
    if '--self-test' in __import__('sys').argv:
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'key.json';save_key('dummy-test-credential-not-real',dest)
            data=json.loads(dest.read_text(encoding='utf-8'))
            assert data['model']=='deepseek-flash' and data['enabled'] is False
            assert data['approved_trial']['max_requests_including_retries']==30
            try:save_key(' ',dest)
            except ValueError:pass
            else:raise AssertionError('empty key accepted')
            assert not list(Path(tmp).glob('.credential-*'))
        print('Credential dialog storage self-test: passed (dummy key only; no network)')
    else:main()
