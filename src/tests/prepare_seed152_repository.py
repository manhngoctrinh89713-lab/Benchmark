"""Restore the synthetic seed152 Git metadata after cloning this project."""
import hashlib,json,shutil,subprocess,tempfile,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
def prepare(initial_root=None):
    initial=Path(initial_root) if initial_root is not None else ROOT/'初始环境/种子152';info=json.loads((initial/'repository_transport.json').read_text(encoding='utf-8'));archive=initial/info['archive'];target=initial/info['gitdir']
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Seed152 repository archive checksum mismatch')
    def verify_head():
        value=(target/'HEAD').read_text(encoding='utf-8').strip()
        if value.startswith('ref: '):
            ref=PurePosixPath(value[5:])
            if ref.is_absolute() or '..' in ref.parts:raise ValueError('Invalid Git HEAD')
            value=target.joinpath(*ref.parts).read_text(encoding='utf-8').strip()
        if value!=info['head']:raise ValueError('Seed152 initial HEAD changed')
    if target.exists():verify_head();return target
    if not target.resolve().is_relative_to(initial.resolve()) or target.name!='.git':raise ValueError('Invalid target')
    with tempfile.TemporaryDirectory(prefix='seed152-prepare-') as td:
        staging=Path(td)/'git';staging.mkdir()
        with zipfile.ZipFile(archive) as z:
            if sum(x.file_size for x in z.infolist())>16*1024*1024:raise ValueError('Oversized metadata')
            for item in z.infolist():
                rel=PurePosixPath(item.filename)
                if rel.is_absolute() or '..' in rel.parts or '\\' in item.filename or ':' in item.filename:raise ValueError('Unsafe metadata path')
                if (item.external_attr>>16)&0o170000==0o120000:raise ValueError('Symlink metadata unsupported')
                path=staging.joinpath(*rel.parts)
                if item.is_dir():path.mkdir(parents=True,exist_ok=True)
                else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(item))
        shutil.copytree(staging,target)
    verify_head();return target
if __name__=='__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8');print('Seed152 prepared: '+str(prepare().parent))
