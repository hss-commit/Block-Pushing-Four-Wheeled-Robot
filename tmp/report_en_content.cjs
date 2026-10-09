const slides=[
[
'Block-Pushing Robot Competition','Design Progress & Strategy','Current progress, pushing strategy and team plan',
'The architecture and strategy are outlined.','Next: hardware selection and prototype tests.',
'Task & system','Match strategy','Plan & teamwork',
'Opponent half','Our half','Starting pose','Start in the opponent half','Face our own half','Pushing objective','Move blocks to our half','Keep them until the finish'
],
[
'Match objective: more blocks in our half',
'The final block count matters.','We must also prevent losses.',
'Starting conditions','Blocks lie near the centerline. Our robot faces our half.',
'Crossing the line','The robot may cross into the opponent half to reposition.',
'Autonomous operation','Each match is under 90 s. External vision and wireless control are allowed.',
'Opponent half','Our half','Starting pose','Start in the opponent half','Face our own half','Pushing objective','Move blocks to our half','Keep them until the finish'
],
[
'System architecture: PC planning, onboard control',
'The PC handles vision and strategy.','The onboard controller handles motion.',
'Vision','Estimate robot pose and block positions in each half.',
'Planning','Select targets and plan approach, push and return actions.',
'Motion control','Track speed commands and stop safely on faults.',
'Overhead camera','Full-field image','External PC','Localization, target selection and action planning',
'Wireless commands','Status','Onboard control board','Motor drivers, encoders and pusher','Wheel speed'
],
[
'Current progress: design outlined, hardware pending',
'Work so far covers requirements, system roles and pushing strategy.',
'Work area','Current progress','Next step','Match requirements','Objective, initial layout and key limits reviewed','Confirm pusher size limits and scoring details',
'System architecture','Vision, planning and control roles defined','Agree on coordinates, messages and fault handling',
'Pushing strategy','Three match phases and one push cycle outlined','Check feasibility through scenarios and prototypes',
'Hardware','Candidates under review, no final selection','Check dimensions, power, drivers and encoders'
],
[
'Strategy framework: retained blocks per cycle',
'Identify groups within the pusher width.','Then compare ',
'expected retention and full cycle time.',
'Target comparison','Expected blocks retained',
'Approach + align + push + release + return',
'Phase','Main action','Decision focus','Opening','Push the group directly ahead','Use the starting pose for a quick first transfer',
'Midgame','Collect, protect or recover blocks','Balance likely gain against opponent interference',
'Endgame','Choose pushes that can finish in time','Allow time for the full action and safe braking'
],
[
'Opening: first transfer from the starting pose',
'We already face the right direction.','Complete a reliable first transfer.',
'Align and push','Push the reachable group ahead. Adjust only when useful.',
'Back off to release','Separate blocks from the pusher before returning.',
'Reposition','Move behind the next target and avoid stored blocks.',
'Opponent half','Our half','Starting pose','First transfer to our half',
'Align and push','Use the group ahead','Balance depth and time',
'Release and return','Back off and check release','Move behind the next group'
],
[
'Midgame: choosing the more valuable target',
'When both robots contest a group,','compare the likely gain first.',
'Check feasibility','The pusher must cover the group, with room to approach.',
'Compare full cycles','Include approach, push, release and return time.',
'Switch if arrival times are close','Avoid wasting time in a head-on pushing contest.',
'Opponent half','Our half','Our robot','Opponent','Target A','Both robots approaching','Higher conflict risk',
'Target B','Possible uncontested push','Reassess as an alternative'
],
[
'Endgame: target choice within the time remaining',
'Choose pushes we can finish.','Include release and stopping time.',
'Estimate the full action','Include approach, alignment, push and release.','Leave a braking margin.',
'Favor nearby targets','Use reachable groups near the line. Limit detours and deep pushes.',
'Confirm release','Check that blocks have left the pusher.','Set the phase switch using measured times.',
'Opponent half','Our half','Distant target','Longer detour and alignment','Lower endgame priority',
'Near-line target','Cross the line and release','Leave time to brake'
],
[
'Implementation plan: one reliable push cycle first',
'After agreeing on parameters and interfaces, develop control and vision in parallel.',
'Confirm inputs','Motion control','Vision prototype','Push-cycle integration','Practice matches',
'Rules and interfaces','Speed loop and wireless control','Calibration and detection','Push, release, return','Repeated cycles and strategy',
'Module tests','Test speed control, detection and fault handling separately.',
'System tests','Stabilize one full cycle, then add midgame and endgame decisions.'
],
[
'Team roles: parallel work, shared system testing',
'Work area','Member A: mechanics & control','Member B: vision & strategy',
'Responsibility','Chassis, pusher, wiring and onboard control','Field calibration, detection and PC planning',
'Development','Motor speed loop, wireless commands and fault stops','Target selection, action state machine and logging',
'Deliverables','Working chassis, wiring guide and control code','Vision outputs, strategy code and calibration files',
'Interface','Execute speed commands and report robot status','Provide coordinates, targets and motion commands',
'Shared work','Strategy, interfaces, integration, practice matches and reporting.'
],
[
'Next milestone: a working, testable prototype',
'At the next review, we aim to show','repeatable robot operation','and recorded test results.',
'Evaluation criteria','Position error, action time, missed blocks and retention',
'Motion control','Wireless speed commands, encoder feedback and fault stops',
'Vision output','Robot pose, block positions and half-field assignment',
'Complete push cycle','Approach, push, release and return, with recorded results'
]
];
const notes=[
`Today we will present our robot design, the block-pushing strategy, and the next steps for our two-person team. We have outlined the system architecture and the main strategy. Hardware selection is still in progress, and we do not yet have confirmed prototype test results. Our next step is to select compatible components and test a working prototype. The field diagrams illustrate decisions and motion. They do not represent measured paths or the final robot design.`,
`The objective is to have more blocks in our half when the match ends. Moving blocks across the centerline is only part of the task, because the opponent can move them back. According to our current requirements, the field is 1.2 meters square and the blocks are about 2 centimeters wide. Our robot starts in the opponent half, facing our half, so the first push can begin directly. The robot may cross the centerline, and it must operate autonomously. External vision and wireless control are allowed. We still need to confirm how the pusher counts toward size limits, and how blocks on the line or inside the pusher are scored.`,
`The overhead camera gives the PC a view of the whole field. The PC estimates positions, selects targets and plans actions. The onboard control board receives speed commands, controls wheel speed and handles fault stops. We have not selected a particular chip or board. For vision, our current plan uses OpenCV color segmentation to detect blocks, and a top marker to estimate robot position and orientation. The boundary between the two members' work is a clear interface for coordinates, speed commands and robot status.`,
`Our completed work is mainly at the design stage. We have reviewed the match requirements, divided the system into functional parts, and outlined a strategy for each phase of the match. We have also researched hardware candidates, but we have not made a final selection. We are not presenting candidate specifications as measured performance. Next, we need to confirm the remaining rule details, check component compatibility and begin prototype validation.`,
`Our strategy focuses on the number of blocks likely to remain in our half at the end. First, we identify groups that fit within the effective pusher width, allowing a margin on each side. We reject groups that cannot be approached safely or reached from the correct side. We then compare the expected number retained against the time for the entire cycle: approach, align, push, release and return. This is a decision principle that still needs testing. In the opening we use the starting position. In the midgame we respond to the opponent. In the endgame we simplify actions to fit the remaining time. Push depth depends on the situation.`,
`At the start, the robot is already on the correct side of the blocks and faces our half. We therefore begin with a group directly ahead, instead of first crossing the line or turning around. A sideways adjustment is useful only if it clearly improves the number of blocks we can cover. We choose the push depth by balancing retention against cycle time. After pushing, the robot backs off slowly and checks that the blocks have separated from the pusher. It then moves behind the next target, avoiding blocks already stored in our half. Solid lines show the push, while dashed lines show a possible return. Actual paths must account for the full pusher width and turning clearance.`,
`In the midgame, we first check whether a target is feasible and then compare the likely gain and full cycle time. In this example, target A may lead to a contest with the opponent, while target B offers another option. These are illustrative positions, not measured arrival times. We consider three actions. We can collect new blocks, push threatened blocks deeper into our half, or recover blocks near the opponent's expected release point. If both robots are likely to arrive at the same time, switching targets can avoid a long head-on contest. We leave safely stored blocks alone. Once a target is selected, we hold it briefly to avoid frequent switching, unless the target changes or a collision risk appears.`,
`Near the end of the match, remaining time becomes the main constraint. We estimate the time needed to approach from the correct side, align, push and release, then add a margin for braking. Reachable blocks close to the centerline usually need less travel than distant targets. We therefore reduce long detours and unnecessary deep pushes. We must still confirm that the blocks have left the pusher. The exact release and stopping behavior will depend on the scoring rules. We will choose when to enter the endgame phase using measured action times, rather than an arbitrary fixed threshold.`,
`We first confirm the rules, component parameters and software interfaces. Then the two workstreams can proceed in parallel. The control workstream tests speed tracking, encoders and wireless commands. The vision workstream tests field calibration, robot pose and block detection. During integration, we first test movement to a point and alignment. We then complete one push, release and return cycle. Only after that cycle is reliable will we add repeated pushes, opponent-aware decisions and phase switching. Dates will depend on component delivery and course milestones. For now, progress will be assessed through working demonstrations and test results.`,
`This is our proposed division of work. Member A handles mechanics, electrical integration and onboard control. Member B handles vision, strategy and the PC program. Before coding independently, we will agree on the coordinate origin, directions, units, command timeout and fault states. Both members will take part in strategy discussions, interface design, integration and practice matches. Each member will also keep clear setup instructions and test records so the other can reproduce the results.`,
`For the next review, our goal is to demonstrate a working prototype with repeatable tests. The control demonstration will show wireless speed commands, encoder feedback and safe stopping on faults. The vision demonstration will show robot pose and block positions. The integrated demonstration will complete a full push cycle and record the result. We will measure position error, action time, missed blocks and the number retained. These will be actual test results rather than assumed performance targets.`
];
module.exports={slides,notes};

