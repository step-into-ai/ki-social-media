"""Prepare the instance-owned regular Chromium for optional feed scrolling; no login import."""
import os,pathlib,shutil,contextlib,io

def main():
    for key in ('CODY_API_TOKEN','CODY_TRANSLATOR_TOKEN','CODY_SPEECH_TOKEN','AI_API_KEY','SPEECH_API_KEY'):os.environ.pop(key,None)
    root=pathlib.Path(os.environ.get('CODY_DATA',pathlib.Path(__file__).resolve().parents[1]/'data'))
    home=root/'reach';home.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.environ.update(HOME=str(home),USERPROFILE=str(home),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'))
    chromium=shutil.which('chromium')
    if not chromium:raise SystemExit('Install regular Chromium before preparing the owned browser.')
    from agent_reach.runtime import browser,tools
    browser.update_state(backend='chrome',executable=chromium,launcher_python=None,fallback_reason='Operator-selected regular packaged Chromium')
    try:
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            tools.ensure('opencli');tools.extend_path();browser.setup()
        if not browser.is_running() or not browser.bound_context():raise ValueError('not ready')
    except Exception as error:
        code=getattr(error,'code',type(error).__name__)
        raise SystemExit('Owned browser setup failed ('+str(code)+'). Inspect toolkit installation and Chromium sandbox support; no raw session data was logged.') from None
    print('Owned Chromium is ready. No platform login or session transfer was performed.')

if __name__=='__main__':main()
