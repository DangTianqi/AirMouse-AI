"""Create user-facing guides and a checked portable archive; standard library only."""
from html import escape
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "dist/AirMouseAI"
RELEASES = ROOT / "releases"
GUIDE = ROOT / "docs/使用说明.md"


def render_guide(markdown: str) -> str:
    """Render this guide's intentionally small Markdown subset without dependencies."""
    result = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("# "):
            result.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("## "):
            result.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("| "):
            table = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            result.append('<div class="table-wrap"><table><thead><tr>' +
                          ''.join(f'<th>{escape(c)}</th>' for c in table[0]) + '</tr></thead><tbody>')
            for row in table[2:]:
                result.append('<tr>' + ''.join(f'<td>{escape(c)}</td>' for c in row) + '</tr>')
            result.append('</tbody></table></div>')
            continue
        elif line.startswith("- "):
            result.append('<ul>')
            while i < len(lines) and lines[i].startswith('- '):
                result.append(f'<li>{escape(lines[i][2:])}</li>')
                i += 1
            result.append('</ul>')
            continue
        else:
            result.append(f'<p>{escape(line)}</p>')
        i += 1
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AirMouse AI 使用说明</title><style>
body{margin:0;background:#f2f5f8;color:#243746;font-family:"Microsoft YaHei UI","Microsoft YaHei",sans-serif;font-size:15px;line-height:1.85}
main{max-width:900px;margin:32px auto;background:white;padding:36px 44px;border-radius:12px;box-shadow:0 4px 24px #2233440d}
h1{font-size:29px;line-height:1.4;color:#16394c;margin-top:0}h2{font-size:21px;margin:30px 0 12px;padding-top:12px;border-top:1px solid #e3eaf0}
p{margin:12px 0}ul{padding-left:24px}li{margin:8px 0}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;margin:16px 0;font-size:14px}
th,td{border:1px solid #d7e2ea;padding:10px 12px;text-align:left;vertical-align:top}th{background:#ecf4f8;color:#16394c}td:first-child{min-width:80px;font-weight:600}
@media(max-width:700px){main{margin:0;padding:24px 18px;border-radius:0}h1{font-size:25px}th,td{padding:8px}}
@media print{body{background:white;font-size:11pt}main{margin:0;padding:0;box-shadow:none;max-width:none}h2{break-after:avoid}tr{break-inside:avoid}.table-wrap{overflow:visible}}
</style></head><body><main>''' + '\n'.join(result) + '</main></body></html>\n'


def main() -> None:
    executable = APP / "AirMouseAI.exe"
    required = [executable, APP / "_internal/assets/models/hand_landmarker.task"]
    if any(not path.is_file() for path in required):
        raise FileNotFoundError("Build the complete onedir application before packaging.")
    markdown = GUIDE.read_text(encoding="utf-8")
    text = '\n'.join(line.removeprefix('# ').removeprefix('## ') for line in markdown.splitlines())
    (APP / "使用说明.txt").write_text(text, encoding="utf-8-sig")
    (APP / "使用说明.html").write_text(render_guide(markdown), encoding="utf-8")
    shutil.copyfile(ROOT / "VALIDATION.md", APP / "测试验证记录.md")
    shutil.copyfile(ROOT / "THIRD_PARTY_NOTICES.md", APP / "第三方说明.md")
    changes=ROOT/'docs/更新说明.md'
    if changes.exists():
        shutil.copyfile(changes,APP/'更新说明.md')
    RELEASES.mkdir(exist_ok=True)
    version=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    archive = RELEASES / f"AirMouseAI-v{version}-Windows-x64.zip"
    staging = archive.with_suffix(".zip.partial")
    files = sorted(path for path in APP.rglob('*') if path.is_file())
    try:
        with zipfile.ZipFile(staging, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as package:
            for path in files:
                package.write(path, path.relative_to(APP.parent).as_posix())
        with zipfile.ZipFile(staging) as package:
            bad = package.testzip()
            if bad:
                raise ValueError(f"Archive CRC verification failed: {bad}")
            names = set(package.namelist())
            if len(names) != len(files):
                raise ValueError("Archive file count mismatch")
            for path in files:
                if package.getinfo(path.relative_to(APP.parent).as_posix()).file_size != path.stat().st_size:
                    raise ValueError(f"Archived file size mismatch: {path}")
        staging.replace(archive)
    finally:
        staging.unlink(missing_ok=True)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    report = {"archive":str(archive), "zip_bytes":archive.stat().st_size,
              "unpacked_bytes":sum(path.stat().st_size for path in files),
              "file_count":len(files), "crc_verified":True, "sha256":digest,
              "exe_sha256":hashlib.sha256(executable.read_bytes()).hexdigest(),
              "status":"trial_ready_manual_acceptance_pending"}
    (ROOT / 'artifacts/release-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
