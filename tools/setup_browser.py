"""Prepare the instance-owned regular Chromium for optional feed scrolling; no login import."""
import os,pathlib,shutil,subprocess

def main():
    for key in ('CODY_API_TOKEN','CODY_TRANSLATOR_TOKEN','CODY_SPEECH_TOKEN','AI_API_KEY','SPEECH_API_KEY'):os.environ.pop(key,None)
    root=pathlib.Path(os.environ.get('CODY_DATA',pathlib.Path(__file__).resolve().parents[1]/'data'))
    home=root/'reach';home.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.environ.update(HOME=str(home),USERPROFILE=str(home),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'))
    chromium=shutil.which('chromium')
    if not chromium:raise SystemExit('Install regular Chromium before preparing the owned browser.')
    from agent_reach.runtime import browser
    browser.update_state(backend='chrome',executable=chromium,launcher_python=None,fallback_reason='Operator-selected regular packaged Chromium')
    result=subprocess.run(['agent-reach','browser','setup'],capture_output=True,text=True,timeout=240)
    if result.returncode:raise SystemExit('Owned browser setup failed. Inspect Chromium sandbox support; no raw session data was logged.')
    print('Owned Chromium is ready. No platform login or session transfer was performed.')

if __name__=='__main__':main()
