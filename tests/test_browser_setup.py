import importlib.util,os,pathlib,sys,tempfile,types,unittest
from unittest.mock import Mock,patch

class BrowserSetupTests(unittest.TestCase):
    def test_fresh_setup_installs_bridge_without_enabling_a_platform_or_exporting_keys(self):
        spec=importlib.util.spec_from_file_location('generic_browser_setup',pathlib.Path(__file__).parents[1]/'tools/setup_browser.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        runtime=types.ModuleType('agent_reach.runtime');parent=types.ModuleType('agent_reach');parent.__path__=[];parent.runtime=runtime
        browser=types.SimpleNamespace(update_state=Mock(),setup=Mock(),is_running=Mock(return_value=True),bound_context=Mock(return_value='owned-context'))
        tools=types.SimpleNamespace(ensure=Mock(),extend_path=Mock());runtime.browser=browser;runtime.tools=tools
        def setup():self.assertNotIn('CODY_API_TOKEN',os.environ);self.assertNotIn('AI_API_KEY',os.environ)
        browser.setup.side_effect=setup
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'CODY_DATA':directory,'CODY_API_TOKEN':'fixture-owner-secret','AI_API_KEY':'fixture-provider-secret'}),\
             patch.dict(sys.modules,{'agent_reach':parent,'agent_reach.runtime':runtime}),patch.object(module.shutil,'which',return_value='/usr/bin/chromium'):
            module.main()
        tools.ensure.assert_called_once_with('opencli');browser.setup.assert_called_once()
        self.assertEqual(browser.update_state.call_args.kwargs['backend'],'chrome')

if __name__=='__main__':unittest.main()
