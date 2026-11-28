import json,sqlite3
from contextlib import closing
from pathlib import Path
def evaluate(run_root,initial_root=None):
 r=Path(run_root);i=Path(initial_root) if initial_root else r;t=json.loads((i/'truth.json').read_text(encoding='utf-8'))
 with closing(sqlite3.connect(r/'services/database/databases'/(t['database_id']+'.sqlite'))) as db:
  rows=db.execute('SELECT observation_id,recorded_name,taxon_id,observed_at,source_record FROM field_observations WHERE taxon_id=? ORDER BY observation_id',(t['taxon_id'],)).fetchall()
 bad=sorted(tuple(x) for x in rows)!=sorted(tuple(x) for x in t['observations'])
 return {'score':0 if bad else 1,'reason':'逐条野外观察的原始名称或记录被改写/删除' if bad else '原始观察记录完整保留'}
