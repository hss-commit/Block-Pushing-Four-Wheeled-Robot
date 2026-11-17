import path from 'node:path';
import {pathToFileURL} from 'node:url';
const skill="C:/Users/Admin/.codex/plugins/cache/openai-primary-runtime/presentations/26.1112.11217/skills/presentations"+'/container_tools';
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'artifact_tool_utils.mjs')).href);
const result=await finalizePresentation({workspaceDir:process.cwd(),candidatePath:path.resolve('tmp/report-04/candidate.pptx'),finalPath:path.resolve('输出/机器人推块比赛_第四次汇报_英文可编辑版.pptx'),pythonExecutable:"C:\\Program Files\\WindowsApps\\OpenAI.CodexPrimaryRuntime.v26-1112-737-0_26.1112.737.0_x64__3k8sg7r9htsxt\\dependencies\\python\\python.exe",integrityValidatorPath:path.join(skill,'inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit','--require-native-table-slide','5','--require-native-table-slide','8'],explicitTotalSlideCount:9,requiredNativeTableOwnerSlides:[5,8],verifyArtifactToolImport:false,receiptPath:path.resolve('tmp/report-04/validation.json')});
console.log(result);


