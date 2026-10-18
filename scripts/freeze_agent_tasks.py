import json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];tasks=[]
genres=[('悬疑','Mystery'),('喜剧','Comedy'),('动作','Action'),('科幻','Sci-Fi'),('爱情','Romance'),('剧情','Drama')]
for family in range(10):
 for i,(cn,en) in enumerate(genres):
  case={'id':f'single-{family:02}-{i}','source':'authored template-generated regression','family':family,'expected_genre':en}
  if family==0:case.update(message=f'想看{cn}电影',kind='recommend')
  elif family==1:case.update(message=f'想看{cn}电影，不要恐怖片',kind='recommend',exclude='Horror')
  elif family==2:case.update(message=f'想看{cn}电影，最好两小时以内',kind='recommend',max_runtime=120)
  elif family==3:case.update(message=f'想看{cn}电影，不要恐怖片，九十分钟以内',kind='recommend',exclude='Horror',max_runtime=90)
  elif family==4:case.update(message=f'想看{cn}电影，不要{cn}电影',kind='clarify')
  elif family==5:case.update(message=f'想看{cn}电影，至少三小时，两小时以内',kind='clarify')
  elif family==6:case.update(message=f'想看节奏快的{cn}电影',kind='unsupported')
  elif family==7:case.update(message=f'以后记住我喜欢{cn}电影',kind='memory')
  elif family==8:case.update(message=f'第一部看过了，想看{cn}电影',kind='clarify')
  else:case.update(message=f'想看{cn}电影，不要恐怖片，120分钟以内',kind='recommend',exclude='Horror',max_runtime=120)
  tasks.append(case)
multi=[]
for family in range(6):
 for i,(cn,en) in enumerate(genres[:5]):
  first=f'想看{cn}电影，不要恐怖片，两小时以内'
  follow=['第一部看过了，换类似的','第一部看过了，换类似的，但不要同一个导演',f'以后记住我不喜欢{cn}电影',f'其实改成恐怖片',f'清空条件，想看{cn}电影',f'想看{cn}电影，至少三小时'][family]
  multi.append({'id':f'multi-{family:02}-{i}','source':'authored template-generated regression','family':family,'messages':[first,follow],'genre':en})
out={'version':'conversation-v1','single':tasks,'multi':multi}
p=root/'eval/agent_tasks.json';p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
(root/'eval/agent_tasks.sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest(),encoding='ascii');print('Frozen tasks:',len(tasks),len(multi))
