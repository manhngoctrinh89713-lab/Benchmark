import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from harness.catalog import ROOT
from harness.environment import apply_private_directories


class Seed35PermissionsTests(unittest.TestCase):
    def test_copied_store_and_moved_key_have_private_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'env'
            shutil.copytree(ROOT / '初始环境/种子35', root)
            apply_private_directories(root)
            project = root / 'workspace/repos/settlement-svc'
            store = project / 'keys/restricted'
            key = store / 'legacy.pem'
            original = project / 'keys/rsa-prod-2023.pem'
            raw = original.read_bytes()
            shutil.move(original, key)
            apply_private_directories(root, create=False)
            self.assertEqual(key.read_bytes(), raw)
            if os.name == 'nt':
                command = "$p='" + str(store).replace("'", "''") + "'; @($p, ($p+'\\legacy.pem')) | ForEach-Object { $a=Get-Acl -LiteralPath $_; [pscustomobject]@{protected=$a.AreAccessRulesProtected; sids=@($a.Access | ForEach-Object {$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value}); inherited=@($a.Access | ForEach-Object {$_.IsInherited})} } | ConvertTo-Json -Depth 4"
                env = dict(os.environ)
                env.pop('PSModulePath', None)
                shell = shutil.which('pwsh') or shutil.which('powershell')
                self.assertIsNotNone(shell, 'PowerShell is required to inspect Windows ACLs')
                result = subprocess.run([shell,'-NoProfile','-Command',command], check=True, capture_output=True, text=True, env=env)
                directory, file = json.loads(result.stdout)
                self.assertTrue(directory['protected'], result.stdout + result.stderr)
                self.assertEqual(len(directory['sids']), 2)
                self.assertIn('S-1-5-18', directory['sids'])
                self.assertEqual(set(file['sids']), set(directory['sids']))
                self.assertTrue(all(file['inherited']))
            else:
                self.assertEqual(store.stat().st_mode & 0o777, 0o700)
                self.assertEqual(key.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
