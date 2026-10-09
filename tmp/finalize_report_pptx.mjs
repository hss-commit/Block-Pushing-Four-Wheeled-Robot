import path from 'node:path';
import {pathToFileURL} from 'node:url';
process.env.RUNTIME_NODE_MODULES='C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const root=process.cwd();
const build=path.join(root,'tmp','ppt-build');
const skill='C:/Users/Admin/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations';
const candidatePath=path.join(build,'candidate.pptx');
const finalPath=path.join(root,'输出','机器人推块比赛_阶段汇报.pptx');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const result=await finalizePresentation({
 workspaceDir:root,candidatePath,finalPath,
 explicitTotalSlideCount:11,
 requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
 pythonExecutable:'C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','18288000,10287000'],
 verifyArtifactToolImport:true,
 receiptPath:path.join(build,'validation.json')
});
console.log(JSON.stringify({finalPath,result},null,2));

