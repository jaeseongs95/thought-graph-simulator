import base64,contextlib,io,json,os,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
from fixtures import ROOT,baseline_path
import common,build_release,build_auto,launch

class Release(unittest.TestCase):
    def test_deterministic_archive_and_embedded_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);a=root/'a.zip';b=root/'b.zip';script=root/'auto.ps1'
            build_release.build(a);build_release.build(b);self.assertEqual(a.read_bytes(),b.read_bytes())
            build_auto.build(a,script);txt=script.read_text(encoding='utf-8-sig')
            embedded=re.search(r"\$EmbeddedSource=@'\n(.*?)\n'@",txt,re.S).group(1)
            self.assertEqual(base64.b64decode(embedded),a.read_bytes());self.assertIn(common.sha(a.read_bytes()),txt)
    def test_install_and_preserve_old_version(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);z=root/'src.zip';build_release.build(z)
            for n,b in common.unzip(z.read_bytes()).items():common.write(root/'release'/n,b)
            source=root/'release/llm_experiments/v075/probe';repo=root/'repo';repo.mkdir()
            marker=repo/'llm_experiments/v074/preserve.txt';common.write(marker,b'old')
            target=launch.install(source,repo);self.assertTrue((target/'run.py').exists());self.assertEqual(marker.read_bytes(),b'old')
            self.assertEqual(launch.install(source,repo),target)
            (target/'run.py').write_bytes(b'changed')
            with self.assertRaises(launch.LaunchError):launch.install(source,repo)
    def test_explicit_baseline_by_content_not_suffix(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);alias=root/'v074_evidence(1).zip';shutil.copyfile(baseline_path(),alias)
            self.assertEqual(launch.choose_baseline(root,alias),alias.resolve())
    def test_wrong_baseline_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);fake=root/'v074_evidence.zip';fake.write_bytes(b'wrong')
            with self.assertRaises(launch.LaunchError):launch.choose_baseline(root,fake)
    def test_auto_no_download_or_model_start_commands(self):
        t=(ROOT/'windows/Auto.template.ps1').read_text(encoding='utf-8-sig')
        for banned in ('Invoke-WebRequest','Start-Service','ollama pull','ollama serve'):self.assertNotIn(banned,t)
        self.assertIn('$LASTEXITCODE',t);self.assertIn('FromBase64String',t)
    def test_launcher_accepts_variable_complete_count(self):
        text=(ROOT/'launch.py').read_text()
        self.assertIn("0 < r.get('inference_calls',-1) <=",text)
        self.assertNotIn("r.get('inference_calls')!=",text)
    @unittest.skipUnless(os.name=='nt' and shutil.which('powershell'), 'Windows PowerShell 네이티브 구문 검사는 Windows에서만 실행')
    def test_windows_powershell_native_parse(self):
        target=str(ROOT/'windows/Auto.template.ps1').replace("'","''")
        cmd="$tokens=$null;$errors=$null;[void][Management.Automation.Language.Parser]::ParseFile('"+target+"',[ref]$tokens,[ref]$errors);if($errors.Count){$errors|Out-String|Write-Output;exit 1};exit 0"
        proc=subprocess.run(['powershell','-NoProfile','-Command',cmd],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)

if __name__=='__main__':unittest.main()
