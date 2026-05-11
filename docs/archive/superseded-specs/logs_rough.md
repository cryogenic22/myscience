2026-04-15T18:18:55.654727042Z [err]  2026-04-15 18:18:53.564 UTC [88632] ERROR:  column "source_type" does not exist at character 25
2026-04-15T18:18:55.654733369Z [err]  2026-04-15 18:18:53.564 UTC [88632] HINT:  Perhaps you meant to reference the column "etl_runs.source_name".
2026-04-15T18:18:55.654737432Z [err]  2026-04-15 18:18:53.564 UTC [88632] STATEMENT:  
2026-04-15T18:18:55.654740710Z [err]  	                SELECT source_type, MAX(finished_at) AS last_run
2026-04-15T18:18:55.654743580Z [err]  	                FROM etl_runs
2026-04-15T18:18:55.654747006Z [err]  	                WHERE status = 'completed'
2026-04-15T18:18:55.654749987Z [err]  	                GROUP BY source_type
2026-04-15T18:18:55.654753393Z [err]  	                HAVING MAX(finished_at) < NOW() - INTERVAL '14 days'
2026-04-15T18:18:55.654756767Z [err]  	                
2026-04-15T18:18:55.654759890Z [err]  2026-04-15 18:18:53.568 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-15T18:18:55.654763482Z [err]  2026-04-15 18:18:53.568 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-15T18:18:55.654766716Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-15T18:18:55.654769979Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-15T18:18:55.654773184Z [err]  	                       VALUES ('34bfcf0d-1034-4992-9e02-6b851233f832', 'bf2036e4-3b4a-4440-aedb-f3f79f062fe1', 'tool_completed', 'data_steward', 'steward_curate', NULL, NULL, 'ok', '{"duration_ms": 13.6}', '2026-04-15T18:18:53.571414+00:00'::timestamptz)
2026-04-15T18:18:55.655286104Z [err]  	                           checkpoint_data = COALESCE(checkpoint_data, '{}'::jsonb) || '{"last_tool": "steward_curate", "status": "ok"}'
2026-04-15T18:18:55.655289592Z [err]  	                       WHERE id = 'bf2036e4-3b4a-4440-aedb-f3f79f062fe1'
2026-04-15T18:18:55.655292487Z [err]  2026-04-15 18:18:53.573 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-15T18:18:55.655295280Z [err]  2026-04-15 18:18:53.573 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-15T18:18:55.655298221Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-15T18:18:55.655301060Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-15T18:18:55.655304041Z [err]  	                       VALUES ('96c73e5e-bdac-47a5-934b-8a20174e71e7', 'bf2036e4-3b4a-4440-aedb-f3f79f062fe1', 'session_checkpoint', 'data_steward', NULL, NULL, NULL, 'ok', '{"step": 1}', '2026-04-15T18:18:53.575891+00:00'::timestamptz)
2026-04-15T18:18:55.655306775Z [err]  2026-04-15 18:18:53.575 UTC [88632] ERROR:  relation "agent_sessions" does not exist at character 8
2026-04-15T18:18:55.655309455Z [err]  2026-04-15 18:18:53.575 UTC [88632] STATEMENT:  UPDATE agent_sessions SET status = 'completed', completed_at = '2026-04-15T18:18:53.578472+00:00'::timestamptz WHERE id = 'bf2036e4-3b4a-4440-aedb-f3f79f062fe1'
2026-04-15T18:18:55.655312298Z [err]  2026-04-15 18:18:53.578 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-15T18:18:55.655314988Z [err]  2026-04-15 18:18:53.578 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-15T18:18:55.655317803Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-15T18:18:55.655320440Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-15T18:18:55.655323318Z [err]  	                       VALUES ('1750e781-39fa-4d8f-9f69-236ee5a5a9fa', 'bf2036e4-3b4a-4440-aedb-f3f79f062fe1', 'session_completed', 'data_steward', NULL, NULL, NULL, 'ok', '{"completed": 1, "failed": 0, "denied": 0}', '2026-04-15T18:18:53.581061+00:00'::timestamptz)
2026-04-15T18:19:55.557760212Z [err]  2026-04-15 18:19:52.176 UTC [86570] LOG:  checkpoint starting: time
2026-04-15T18:19:55.557763052Z [err]  2026-04-15 18:19:53.100 UTC [86570] LOG:  checkpoint complete: wrote 9 buffers (0.1%), wrote 1 SLRU buffers; 0 WAL file(s) added, 0 removed, 0 recycled; write=0.905 s, sync=0.007 s, total=0.924 s; sync files=6, longest=0.005 s, average=0.002 s; distance=51 kB, estimate=15743 kB; lsn=D/65F231C8, redo lsn=D/65F23170
2026-04-15T18:24:58.771891773Z [err]  2026-04-15 18:24:52.198 UTC [86570] LOG:  checkpoint starting: time
2026-04-15T18:24:58.771894970Z [err]  2026-04-15 18:24:54.434 UTC [86570] LOG:  checkpoint complete: wrote 22 buffers (0.1%), wrote 1 SLRU buffers; 0 WAL file(s) added, 1 removed, 0 recycled; write=2.209 s, sync=0.010 s, total=2.237 s; sync files=33, longest=0.004 s, average=0.001 s; distance=1360 kB, estimate=14304 kB; lsn=D/66077250, redo lsn=D/660771F8
2026-04-15T20:21:25.877143553Z [err]  2026-04-15 20:21:16.046 UTC [88632] ERROR:  relation "agent_sessions" does not exist at character 13
2026-04-15T20:21:25.877148006Z [err]  2026-04-15 20:21:16.046 UTC [88632] STATEMENT:  INSERT INTO agent_sessions (id, agent_type, goal, status, total_steps, started_at)
2026-04-15T20:21:25.877151633Z [err]  	                       VALUES ('e1128979-fbe1-412f-9133-1c16a1b6e38d', 'data_steward', 'Periodic curation cycle 106', 'running', 1, '2026-04-15T20:21:16.048539+00:00'::timestamptz)
2026-04-15T20:21:25.877154942Z [err]  2026-04-15 20:21:16.048 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-15T20:21:25.877158499Z [err]  2026-04-15 20:21:16.048 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-15T20:21:25.877162271Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-15T20:21:25.877165922Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-15T20:21:25.877169282Z [err]  	                       VALUES ('129a1804-8564-4c07-baf6-e80969fd07e6', 'e1128979-fbe1-412f-9133-1c16a1b6e38d', 'turn_start', 'data_steward', NULL, NULL, NULL, 'ok', '{"goal": "Periodic curation cycle 106", "total_steps": 1}', '2026-04-15T20:21:16.051664+00:00'::timestamptz)
2026-04-15T20:21:25.877172260Z [err]  2026-04-15 20:21:16.051 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-15T20:21:25.877175682Z [err]  2026-04-15 20:21:16.051 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-15T20:21:25.877178440Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-15T20:21:25.877181339Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-15T20:21:25.877184260Z [err]  	                       VALUES ('68095b32-74b6-4cb3-b7ff-d7b01ff0c05d', 'e1128979-fbe1-412f-9133-1c16a1b6e38d', 'tool_invoked', 'data_steward', 'steward_curate', 'standard', 'e90f0cec871513d3', 'ok', '{}', '2026-04-15T20:21:16.054414+00:00'::timestamptz)
2026-04-15T20:21:25.877895918Z [err]  2026-04-15 20:21:16.068 UTC [88632] ERROR:  relation "agent_sessions" does not exist at character 8
2026-04-15T20:21:25.877902125Z [err]  2026-04-15 20:21:16.068 UTC [88632] STATEMENT:  UPDATE agent_sessions
2026-04-15T20:21:25.877905627Z [err]  	                       SET current_step = 1, last_checkpoint = '2026-04-15T20:21:16.070964+00:00'::timestamptz,
2026-04-15T20:21:25.877912671Z [err]  2026-04-15 20:21:16.061 UTC [88632] ERROR:  column "source_type" does not exist at character 25
2026-04-15T20:21:25.877917973Z [err]  2026-04-15 20:21:16.061 UTC [88632] HINT:  Perhaps you meant to reference the column "etl_runs.source_name".
2026-04-15T20:21:25.877921335Z [err]  2026-04-15 20:21:16.061 UTC [88632] STATEMENT:  
2026-04-15T20:21:25.877924315Z [err]  	                SELECT source_type, MAX(finished_at) AS last_run
2026-04-15T20:21:25.877928096Z [err]  	                FROM etl_runs
2026-04-15T20:21:25.877930829Z [err]  	                WHERE status = 'completed'
2026-04-15T20:21:25.877933386Z [err]  	                GROUP BY source_type
2026-04-15T20:21:25.877936207Z [err]  	                HAVING MAX(finished_at) < NOW() - INTERVAL '14 days'
2026-04-15T20:21:25.877939156Z [err]  	                
2026-04-15T20:21:25.877942195Z [err]  2026-04-15 20:21:16.065 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-15T20:21:25.877945196Z [err]  2026-04-15 20:21:16.065 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-15T20:21:25.877947825Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-15T20:21:25.877950545Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-15T20:21:25.877953140Z [err]  	                       VALUES ('2ae0a7a5-e4f3-4e7e-8997-ed836ba617eb', 'e1128979-fbe1-412f-9133-1c16a1b6e38d', 'tool_completed', 'data_steward', 'steward_curate', NULL, NULL, 'ok', '{"duration_ms": 14.3}', '2026-04-15T20:21:16.068660+00:00'::timestamptz)
2026-04-15T20:21:25.878664106Z [err]  	                           checkpoint_data = COALESCE(checkpoint_data, '{}'::jsonb) || '{"last_tool": "steward_curate", "status": "ok"}'
2026-04-15T20:21:25.878668794Z [err]  	                       WHERE id = 'e1128979-fbe1-412f-9133-1c16a1b6e38d'
2026-04-15T20:21:25.878673608Z [err]  2026-04-15 20:21:16.070 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-15T20:21:25.878678468Z [err]  2026-04-15 20:21:16.070 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-15T20:21:25.878684330Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-15T20:21:25.878688663Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-15T20:21:25.878692812Z [err]  	                       VALUES ('d27c6dfb-1ccf-4849-9d75-70684be2f219', 'e1128979-fbe1-412f-9133-1c16a1b6e38d', 'session_checkpoint', 'data_steward', NULL, NULL, NULL, 'ok', '{"step": 1}', '2026-04-15T20:21:16.073531+00:00'::timestamptz)
2026-04-15T20:21:25.878697007Z [err]  2026-04-15 20:21:16.072 UTC [88632] ERROR:  relation "agent_sessions" does not exist at character 8
2026-04-15T20:21:25.878701340Z [err]  2026-04-15 20:21:16.072 UTC [88632] STATEMENT:  UPDATE agent_sessions SET status = 'completed', completed_at = '2026-04-15T20:21:16.075782+00:00'::timestamptz WHERE id = 'e1128979-fbe1-412f-9133-1c16a1b6e38d'
2026-04-15T20:21:25.878708525Z [err]  2026-04-15 20:21:16.075 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-15T20:21:25.878712547Z [err]  2026-04-15 20:21:16.075 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-15T20:21:25.878717329Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-15T20:21:25.878721858Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-15T20:21:25.878725649Z [err]  	                       VALUES ('f13b8f41-32d6-4e91-b67d-6e274abba846', 'e1128979-fbe1-412f-9133-1c16a1b6e38d', 'session_completed', 'data_steward', NULL, NULL, NULL, 'ok', '{"completed": 1, "failed": 0, "denied": 0}', '2026-04-15T20:21:16.077873+00:00'::timestamptz)
2026-04-15T22:21:16.883887473Z [err]  	                       VALUES ('0c8da1bb-6cae-4687-9047-d3010b23ee96', 'f6935c6e-070b-4a53-bd43-d24498ee57be', 'turn_start', 'data_steward', NULL, NULL, NULL, 'ok', '{"goal": "Periodic curation cycle 107", "total_steps": 1}', '2026-04-15T22:21:16.085042+00:00'::timestamptz)
2026-04-15T22:21:16.883895219Z [err]  2026-04-15 22:21:16.087 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-15T22:21:16.883901465Z [err]  2026-04-15 22:21:16.087 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-15T22:21:16.883902838Z [err]  2026-04-15 22:21:16.082 UTC [88632] ERROR:  relation "agent_sessions" does not exist at character 13
2026-04-15T22:21:16.883907564Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-15T22:21:16.883908088Z [err]  2026-04-15 22:21:16.082 UTC [88632] STATEMENT:  INSERT INTO agent_sessions (id, agent_type, goal, status, total_steps, started_at)
2026-04-15T22:21:16.883913316Z [err]  	                       VALUES ('f6935c6e-070b-4a53-bd43-d24498ee57be', 'data_steward', 'Periodic curation cycle 107', 'running', 1, '2026-04-15T22:21:16.082047+00:00'::timestamptz)
2026-04-15T22:21:16.883914166Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-15T22:21:16.883919383Z [err]  2026-04-15 22:21:16.085 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-15T22:21:16.883920879Z [err]  	                       VALUES ('a78a424a-5a77-4c9b-ad7f-b23b6e9f4106', 'f6935c6e-070b-4a53-bd43-d24498ee57be', 'tool_invoked', 'data_steward', 'steward_curate', 'standard', 'e90f0cec871513d3', 'ok', '{}', '2026-04-15T22:21:16.087965+00:00'::timestamptz)
2026-04-15T22:21:16.883924039Z [err]  2026-04-15 22:21:16.085 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-15T22:21:16.883927443Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-15T22:21:16.883930911Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-15T22:21:16.884928115Z [err]  2026-04-15 22:21:16.097 UTC [88632] ERROR:  column "source_type" does not exist at character 25
2026-04-15T22:21:16.884932225Z [err]  2026-04-15 22:21:16.097 UTC [88632] HINT:  Perhaps you meant to reference the column "etl_runs.source_name".
2026-04-15T22:21:16.884935074Z [err]  2026-04-15 22:21:16.097 UTC [88632] STATEMENT:  
2026-04-15T22:21:16.884939032Z [err]  	                SELECT source_type, MAX(finished_at) AS last_run
2026-04-15T22:21:16.884942448Z [err]  	                FROM etl_runs
2026-04-15T22:21:16.884945846Z [err]  	                WHERE status = 'completed'
2026-04-15T22:21:16.884949009Z [err]  	                GROUP BY source_type
2026-04-15T22:21:16.884952043Z [err]  	                HAVING MAX(finished_at) < NOW() - INTERVAL '14 days'
2026-04-15T22:21:16.884955086Z [err]  	                
2026-04-15T22:21:16.884958392Z [err]  2026-04-15 22:21:16.101 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-15T22:21:16.884962392Z [err]  2026-04-15 22:21:16.101 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-15T22:21:16.884965582Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-15T22:21:16.884968273Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-15T22:21:16.884971065Z [err]  	                       VALUES ('3776528a-2ed5-48ab-a68e-d12c6d714345', 'f6935c6e-070b-4a53-bd43-d24498ee57be', 'tool_completed', 'data_steward', 'steward_curate', NULL, NULL, 'ok', '{"duration_ms": 14.3}', '2026-04-15T22:21:16.102183+00:00'::timestamptz)
2026-04-15T22:21:16.884974017Z [err]  2026-04-15 22:21:16.104 UTC [88632] ERROR:  relation "agent_sessions" does not exist at character 8
2026-04-15T22:21:16.884976940Z [err]  2026-04-15 22:21:16.104 UTC [88632] STATEMENT:  UPDATE agent_sessions
2026-04-15T22:21:16.884980586Z [err]  	                       SET current_step = 1, last_checkpoint = '2026-04-15T22:21:16.104580+00:00'::timestamptz,
2026-04-15T22:21:16.886216108Z [err]  	                           checkpoint_data = COALESCE(checkpoint_data, '{}'::jsonb) || '{"last_tool": "steward_curate", "status": "ok"}'
2026-04-15T22:21:16.886219375Z [err]  	                       WHERE id = 'f6935c6e-070b-4a53-bd43-d24498ee57be'
2026-04-15T22:21:16.886222605Z [err]  2026-04-15 22:21:16.106 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-15T22:21:16.886226037Z [err]  2026-04-15 22:21:16.106 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-15T22:21:16.886230731Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-15T22:21:16.886234421Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-15T22:21:16.886237892Z [err]  	                       VALUES ('617ff7c6-038d-4e0b-a310-0f15bb4b1dae', 'f6935c6e-070b-4a53-bd43-d24498ee57be', 'session_checkpoint', 'data_steward', NULL, NULL, NULL, 'ok', '{"step": 1}', '2026-04-15T22:21:16.107099+00:00'::timestamptz)
2026-04-15T22:21:16.886241425Z [err]  2026-04-15 22:21:16.109 UTC [88632] ERROR:  relation "agent_sessions" does not exist at character 8
2026-04-15T22:21:16.886244940Z [err]  2026-04-15 22:21:16.109 UTC [88632] STATEMENT:  UPDATE agent_sessions SET status = 'completed', completed_at = '2026-04-15T22:21:16.109801+00:00'::timestamptz WHERE id = 'f6935c6e-070b-4a53-bd43-d24498ee57be'
2026-04-15T22:21:16.886248519Z [err]  2026-04-15 22:21:16.111 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-15T22:21:16.886251650Z [err]  2026-04-15 22:21:16.111 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-15T22:21:16.886255465Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-15T22:21:16.886258420Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-15T22:21:16.886261570Z [err]  	                       VALUES ('cc75a592-e653-40db-8d6f-646b25e92da9', 'f6935c6e-070b-4a53-bd43-d24498ee57be', 'session_completed', 'data_steward', NULL, NULL, NULL, 'ok', '{"completed": 1, "failed": 0, "denied": 0}', '2026-04-15T22:21:16.112219+00:00'::timestamptz)
2026-04-16T00:21:26.077302247Z [err]  2026-04-16 00:21:16.117 UTC [88632] ERROR:  relation "agent_sessions" does not exist at character 13
2026-04-16T00:21:26.077307547Z [err]  2026-04-16 00:21:16.117 UTC [88632] STATEMENT:  INSERT INTO agent_sessions (id, agent_type, goal, status, total_steps, started_at)
2026-04-16T00:21:26.077312007Z [err]  	                       VALUES ('74312172-68c4-4820-a57a-77ecce6ea2ed', 'data_steward', 'Periodic curation cycle 108', 'running', 1, '2026-04-16T00:21:16.115895+00:00'::timestamptz)
2026-04-16T00:21:26.077316500Z [err]  2026-04-16 00:21:16.120 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-16T00:21:26.077320857Z [err]  2026-04-16 00:21:16.120 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-16T00:21:26.077324865Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-16T00:21:26.077329093Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-16T00:21:26.077333830Z [err]  	                       VALUES ('e15e038c-c0e5-4225-ab70-6fbb80a33f4d', '74312172-68c4-4820-a57a-77ecce6ea2ed', 'turn_start', 'data_steward', NULL, NULL, NULL, 'ok', '{"goal": "Periodic curation cycle 108", "total_steps": 1}', '2026-04-16T00:21:16.118927+00:00'::timestamptz)
2026-04-16T00:21:26.077338199Z [err]  2026-04-16 00:21:16.123 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-16T00:21:26.077342526Z [err]  2026-04-16 00:21:16.123 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-16T00:21:26.077346426Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-16T00:21:26.077350285Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-16T00:21:26.077355419Z [err]  	                       VALUES ('0c24577a-e42a-4cfc-af07-1087187c0349', '74312172-68c4-4820-a57a-77ecce6ea2ed', 'tool_invoked', 'data_steward', 'steward_curate', 'standard', 'e90f0cec871513d3', 'ok', '{}', '2026-04-16T00:21:16.121446+00:00'::timestamptz)
2026-04-16T00:21:26.077890764Z [err]  2026-04-16 00:21:16.132 UTC [88632] ERROR:  column "source_type" does not exist at character 25
2026-04-16T00:21:26.077898609Z [err]  2026-04-16 00:21:16.132 UTC [88632] HINT:  Perhaps you meant to reference the column "etl_runs.source_name".
2026-04-16T00:21:26.077902982Z [err]  2026-04-16 00:21:16.132 UTC [88632] STATEMENT:  
2026-04-16T00:21:26.077906442Z [err]  	                SELECT source_type, MAX(finished_at) AS last_run
2026-04-16T00:21:26.077910579Z [err]  	                FROM etl_runs
2026-04-16T00:21:26.077913949Z [err]  	                WHERE status = 'completed'
2026-04-16T00:21:26.077917381Z [err]  	                GROUP BY source_type
2026-04-16T00:21:26.077920907Z [err]  	                HAVING MAX(finished_at) < NOW() - INTERVAL '14 days'
2026-04-16T00:21:26.077924198Z [err]  	                
2026-04-16T00:21:26.077927871Z [err]  2026-04-16 00:21:16.138 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-16T00:21:26.077931268Z [err]  2026-04-16 00:21:16.138 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-16T00:21:26.077936367Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-16T00:21:26.077939893Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-16T00:21:26.077943097Z [err]  	                       VALUES ('efc27502-9fb9-46cb-be25-da409499c9d4', '74312172-68c4-4820-a57a-77ecce6ea2ed', 'tool_completed', 'data_steward', 'steward_curate', NULL, NULL, 'ok', '{"duration_ms": 15.1}', '2026-04-16T00:21:16.136487+00:00'::timestamptz)
2026-04-16T00:21:26.077946548Z [err]  2026-04-16 00:21:16.140 UTC [88632] ERROR:  relation "agent_sessions" does not exist at character 8
2026-04-16T00:21:26.077950241Z [err]  2026-04-16 00:21:16.140 UTC [88632] STATEMENT:  UPDATE agent_sessions
2026-04-16T00:21:26.077954334Z [err]  	                       SET current_step = 1, last_checkpoint = '2026-04-16T00:21:16.138824+00:00'::timestamptz,
2026-04-16T00:21:26.078406845Z [err]  	                           checkpoint_data = COALESCE(checkpoint_data, '{}'::jsonb) || '{"last_tool": "steward_curate", "status": "ok"}'
2026-04-16T00:21:26.078411396Z [err]  	                       WHERE id = '74312172-68c4-4820-a57a-77ecce6ea2ed'
2026-04-16T00:21:26.078414210Z [err]  2026-04-16 00:21:16.142 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-16T00:21:26.078416924Z [err]  2026-04-16 00:21:16.142 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-16T00:21:26.078421029Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-16T00:21:26.078424450Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-16T00:21:26.078428475Z [err]  	                       VALUES ('c4b70312-88af-48c8-8acf-aeae123992ca', '74312172-68c4-4820-a57a-77ecce6ea2ed', 'session_checkpoint', 'data_steward', NULL, NULL, NULL, 'ok', '{"step": 1}', '2026-04-16T00:21:16.141055+00:00'::timestamptz)
2026-04-16T00:21:26.078432340Z [err]  2026-04-16 00:21:16.144 UTC [88632] ERROR:  relation "agent_sessions" does not exist at character 8
2026-04-16T00:21:26.078436046Z [err]  2026-04-16 00:21:16.144 UTC [88632] STATEMENT:  UPDATE agent_sessions SET status = 'completed', completed_at = '2026-04-16T00:21:16.143342+00:00'::timestamptz WHERE id = '74312172-68c4-4820-a57a-77ecce6ea2ed'
2026-04-16T00:21:26.078439666Z [err]  2026-04-16 00:21:16.146 UTC [88632] ERROR:  relation "agent_events" does not exist at character 13
2026-04-16T00:21:26.078443759Z [err]  2026-04-16 00:21:16.146 UTC [88632] STATEMENT:  INSERT INTO agent_events
2026-04-16T00:21:26.078447762Z [err]  	                       (id, session_id, event_type, agent_type, tool_name,
2026-04-16T00:21:26.078451941Z [err]  	                        trust_tier, args_hash, result_status, metadata, created_at)
2026-04-16T00:21:26.078455662Z [err]  	                       VALUES ('90069ecf-3d13-4998-9daf-7460e348aeb8', '74312172-68c4-4820-a57a-77ecce6ea2ed', 'session_completed', 'data_steward', NULL, NULL, NULL, 'ok', '{"completed": 1, "failed": 0, "denied": 0}', '2026-04-16T00:21:16.145405+00:00'::timestamptz)
2026-04-16T00:21:26.079228146Z [err]  2026-04-16 00:21:16.804 UTC [89518] ERROR:  function min(uuid) does not exist at character 61
2026-04-16T00:21:26.079231844Z [err]  2026-04-16 00:21:16.804 UTC [89518] HINT:  No function matches the given name and argument types. You might need to add explicit type casts.
2026-04-16T00:21:26.079235392Z [err]  2026-04-16 00:21:16.804 UTC [89518] STATEMENT:  
2026-04-16T00:21:26.079238414Z [err]  	                WITH dupes AS (
2026-04-16T00:21:26.079241193Z [err]  	                    SELECT MIN(id) AS keep_id, source_entity_id, target_entity_id, link_type
2026-04-16T00:21:26.079244388Z [err]  	                    FROM entity_links
2026-04-16T00:21:26.079247125Z [err]  	                    GROUP BY source_entity_id, target_entity_id, link_type
2026-04-16T00:21:26.079249944Z [err]  	                    HAVING COUNT(*) > 1
2026-04-16T00:21:26.079252990Z [err]  	                )
2026-04-16T00:21:26.079255620Z [err]  	                DELETE FROM entity_links
2026-04-16T00:21:26.079258286Z [err]  	                WHERE id IN (
2026-04-16T00:21:26.079260914Z [err]  	                    SELECT el.id FROM entity_links el
2026-04-16T00:21:26.079263525Z [err]  	                    JOIN dupes d ON el.source_entity_id = d.source_entity_id
2026-04-16T00:21:26.079266117Z [err]  	                        AND el.target_entity_id = d.target_entity_id
2026-04-16T00:21:26.079268737Z [err]  	                        AND el.link_type = d.link_type
2026-04-16T00:21:26.079271387Z [err]  	                        AND el.id != d.keep_id
2026-04-16T00:21:26.079273877Z [err]  	                )
2026-04-16T00:21:26.079276451Z [err]  	                
2026-04-16T00:22:06.000921026Z [err]  2026-04-16 00:21:59.481 UTC [89525] ERROR:  column "label" does not exist at character 95
2026-04-16T00:22:06.000928433Z [err]  2026-04-16 00:21:59.481 UTC [89525] STATEMENT:  
2026-04-16T00:22:06.000933249Z [err]  	                    SELECT COUNT(*) AS filled FROM clinical_trials
2026-04-16T00:22:06.000937061Z [err]  	                    WHERE label IS NOT NULL
2026-04-16T00:22:06.000941390Z [err]  	                      AND label::text != ''
2026-04-16T00:22:06.000945357Z [err]  	                      AND label::text != '{}'
2026-04-16T00:22:06.000950224Z [err]  	                    
2026-04-16T00:22:06.000955767Z [err]  2026-04-16 00:22:05.771 UTC [89551] ERROR:  could not write to file "base/pgsql_tmp/pgsql_tmp89551.0": No space left on device
2026-04-16T00:22:06.000959724Z [err]  2026-04-16 00:22:05.771 UTC [89551] STATEMENT:  SELECT COUNT(*) AS multi, SUM(1) AS total
2026-04-16T00:22:06.000963390Z [err]  	                   FROM (
2026-04-16T00:22:06.000967239Z [err]  	                       SELECT entity_id
2026-04-16T00:22:06.000971371Z [err]  	                       FROM (
2026-04-16T00:22:06.000975645Z [err]  	                           SELECT source_entity_id AS entity_id, source_entity_type AS etype
2026-04-16T00:22:06.000980864Z [err]  	                           FROM entity_links
2026-04-16T00:22:06.000985947Z [err]  	                           WHERE link_type != 'COMPETES_WITH'
2026-04-16T00:22:06.000990293Z [err]  	                           UNION ALL
2026-04-16T00:22:06.000994933Z [err]  	                           SELECT target_entity_id, target_entity_type
2026-04-16T00:22:06.000998667Z [err]  	                           FROM entity_links
2026-04-16T00:22:06.001002390Z [err]  	                           WHERE link_type != 'COMPETES_WITH'
2026-04-16T00:22:06.001006527Z [err]  	                       ) sub
2026-04-16T00:22:06.001015060Z [err]  	                       GROUP BY entity_id
2026-04-16T00:22:06.001080907Z [err]  	                       HAVING COUNT(DISTINCT etype) >= 2
2026-04-16T00:22:06.001085298Z [err]  	                   ) multi_source
2026-04-16T00:25:08.515462032Z [err]  2026-04-16 00:24:59.624 UTC [86570] LOG:  checkpoint starting: time
2026-04-16T00:25:08.515465220Z [err]  2026-04-16 00:25:02.665 UTC [86570] LOG:  checkpoint complete: wrote 30 buffers (0.2%), wrote 2 SLRU buffers; 0 WAL file(s) added, 0 removed, 0 recycled; write=3.013 s, sync=0.015 s, total=3.042 s; sync files=120, longest=0.004 s, average=0.001 s; distance=10483 kB, estimate=13922 kB; lsn=D/66AB4230, redo lsn=D/66AB41A0
2026-04-16T02:00:08.533115426Z [err]  2026-04-16 02:00:01.556 UTC [86570] LOG:  checkpoint starting: time
2026-04-16T02:00:08.533122728Z [err]  2026-04-16 02:00:01.981 UTC [86570] LOG:  checkpoint complete: wrote 4 buffers (0.0%), wrote 1 SLRU buffers; 0 WAL file(s) added, 0 removed, 0 recycled; write=0.404 s, sync=0.007 s, total=0.425 s; sync files=5, longest=0.005 s, average=0.002 s; distance=19 kB, estimate=12532 kB; lsn=D/66AB8E00, redo lsn=D/66AB8DA8
2026-04-16T02:05:11.282288859Z [err]  2026-04-16 02:05:01.912 UTC [86570] LOG:  checkpoint starting: time
2026-04-16T02:06:51.486587831Z [err]  	            
2026-04-16T02:06:51.486596531Z [err]  2026-04-16 02:06:45.144 UTC [7] LOG:  terminating any other active server processes
2026-04-16T02:06:51.486605067Z [err]  2026-04-16 02:06:45.139 UTC [89997] PANIC:  could not write to file "pg_wal/xlogtemp.89997": No space left on device
2026-04-16T02:06:51.486610011Z [err]  2026-04-16 02:06:45.139 UTC [89997] STATEMENT:  
2026-04-16T02:06:51.486613484Z [err]  	            INSERT INTO trial_locations
2026-04-16T02:06:51.486616894Z [err]  	                (trial_id, facility_name, city, state, country, status,
2026-04-16T02:06:51.486624539Z [err]  	                 source_api, source_url, retrieved_at)
2026-04-16T02:06:51.486629650Z [err]  	            VALUES ('NCT05726227', 'UZ Antwerpen - UZA - Kinderziekenhuis', 'Edegem', NULL, 'Belgium', NULL, 'clinical_trials_gov', 'https://clinicaltrials.gov/api/v2/studies?query.term=NCT05726227', '2026-04-16T02:00:03.601568'::timestamp)
2026-04-16T02:06:51.486633454Z [err]  	            RETURNING id
2026-04-16T02:06:51.486637556Z [err]  	            
2026-04-16T02:06:51.486640692Z [err]  2026-04-16 02:06:45.144 UTC [7] LOG:  client backend (PID 89997) was terminated by signal 6: Aborted
2026-04-16T02:06:51.486644043Z [err]  2026-04-16 02:06:45.144 UTC [7] DETAIL:  Failed process was running: 
2026-04-16T02:06:51.486647511Z [err]  	            INSERT INTO trial_locations
2026-04-16T02:06:51.486650946Z [err]  	                (trial_id, facility_name, city, state, country, status,
2026-04-16T02:06:51.486653997Z [err]  	                 source_api, source_url, retrieved_at)
2026-04-16T02:06:51.486657229Z [err]  	            VALUES ('NCT05726227', 'UZ Antwerpen - UZA - Kinderziekenhuis', 'Edegem', NULL, 'Belgium', NULL, 'clinical_trials_gov', 'https://clinicaltrials.gov/api/v2/studies?query.term=NCT05726227', '2026-04-16T02:00:03.601568'::timestamp)
2026-04-16T02:06:51.486660368Z [err]  	            RETURNING id
2026-04-16T02:06:51.487076014Z [err]  2026-04-16 02:06:45.151 UTC [7] LOG:  all server processes terminated; reinitializing
2026-04-16T02:06:51.487083141Z [err]  2026-04-16 02:06:45.181 UTC [90007] LOG:  database system was interrupted; last known up at 2026-04-16 02:00:01 UTC
2026-04-16T02:06:51.487086765Z [err]  2026-04-16 02:06:45.253 UTC [90007] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-16T02:06:51.487090896Z [err]  2026-04-16 02:06:45.257 UTC [90007] LOG:  redo starts at D/66AB8DA8
2026-04-16T02:06:51.487094472Z [err]  2026-04-16 02:06:45.806 UTC [90007] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.27 s, system: 0.27 s, elapsed: 0.54 s
2026-04-16T02:06:51.487098105Z [err]  2026-04-16 02:06:45.842 UTC [90007] FATAL:  could not write to file "pg_wal/xlogtemp.90007": No space left on device
2026-04-16T02:06:51.487101989Z [err]  2026-04-16 02:06:45.847 UTC [7] LOG:  startup process (PID 90007) exited with exit code 1
2026-04-16T02:06:51.487105572Z [err]  2026-04-16 02:06:45.847 UTC [7] LOG:  terminating any other active server processes
2026-04-16T02:06:51.487109196Z [err]  2026-04-16 02:06:45.848 UTC [7] LOG:  shutting down due to startup process failure
2026-04-16T02:06:51.487112748Z [err]  2026-04-16 02:06:45.859 UTC [7] LOG:  database system is shut down
2026-04-16T02:06:55.742306360Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-16T02:06:55.910971273Z [inf]  Certificate will not expire
2026-04-16T02:06:55.968259905Z [inf]  
2026-04-16T02:06:55.968264564Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-16T02:06:55.968268783Z [inf]  
2026-04-16T02:06:55.995013883Z [err]  2026-04-16 02:06:55.991 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-16T02:06:55.995018536Z [err]  2026-04-16 02:06:55.991 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-16T02:06:55.995022591Z [err]  2026-04-16 02:06:55.991 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-16T02:06:56.000355358Z [err]  2026-04-16 02:06:55.998 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-16T02:06:56.011469950Z [err]  2026-04-16 02:06:56.007 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-16 02:06:45 UTC
2026-04-16T02:06:56.011474193Z [err]  2026-04-16 02:06:56.007 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-16T02:06:56.083426574Z [err]  2026-04-16 02:06:56.080 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-16T02:06:56.089003306Z [err]  2026-04-16 02:06:56.085 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-16T02:06:56.945503560Z [err]  2026-04-16 02:06:56.889 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.26 s, system: 0.39 s, elapsed: 0.80 s
2026-04-16T02:06:56.945510529Z [err]  2026-04-16 02:06:56.910 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-16T02:06:56.945514499Z [err]  2026-04-16 02:06:56.915 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-16T02:06:56.945518713Z [err]  2026-04-16 02:06:56.915 UTC [7] LOG:  terminating any other active server processes
2026-04-16T02:06:56.945522600Z [err]  2026-04-16 02:06:56.916 UTC [7] LOG:  shutting down due to startup process failure
2026-04-16T02:06:56.945526651Z [err]  2026-04-16 02:06:56.927 UTC [7] LOG:  database system is shut down
2026-04-16T02:07:05.621132314Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-16T02:07:05.817901126Z [inf]  Certificate will not expire
2026-04-16T02:07:05.845477879Z [inf]  
2026-04-16T02:07:05.845482136Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-16T02:07:05.845485116Z [inf]  
2026-04-16T02:07:05.885983442Z [err]  2026-04-16 02:07:05.873 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-16T02:07:05.885988096Z [err]  2026-04-16 02:07:05.873 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-16T02:07:05.885992882Z [err]  2026-04-16 02:07:05.873 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-16T02:07:05.885995775Z [err]  2026-04-16 02:07:05.880 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-16T02:07:05.891346840Z [err]  2026-04-16 02:07:05.890 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-16 02:06:56 UTC
2026-04-16T02:07:05.891353290Z [err]  2026-04-16 02:07:05.890 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-16T02:07:05.961475412Z [err]  2026-04-16 02:07:05.960 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-16T02:07:05.966708726Z [err]  2026-04-16 02:07:05.964 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-16T02:07:06.776388173Z [err]  2026-04-16 02:07:06.766 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.30 s, system: 0.35 s, elapsed: 0.80 s
2026-04-16T02:07:06.789148043Z [err]  2026-04-16 02:07:06.785 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-16T02:07:06.794562852Z [err]  2026-04-16 02:07:06.791 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-16T02:07:06.794567181Z [err]  2026-04-16 02:07:06.791 UTC [7] LOG:  terminating any other active server processes
2026-04-16T02:07:06.794574921Z [err]  2026-04-16 02:07:06.791 UTC [7] LOG:  shutting down due to startup process failure
2026-04-16T02:07:06.807733341Z [err]  2026-04-16 02:07:06.802 UTC [7] LOG:  database system is shut down
2026-04-16T02:07:16.605398948Z [inf]  Certificate will not expire
2026-04-16T02:07:16.957165484Z [inf]  
2026-04-16T02:07:16.957170431Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-16T02:07:16.957173874Z [inf]  
2026-04-16T02:07:16.957177360Z [err]  2026-04-16 02:07:16.680 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-16T02:07:16.957182006Z [err]  2026-04-16 02:07:16.680 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-16T02:07:16.957185045Z [err]  2026-04-16 02:07:16.680 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-16T02:07:16.957187931Z [err]  2026-04-16 02:07:16.688 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-16T02:07:16.957190754Z [err]  2026-04-16 02:07:16.698 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-16 02:07:05 UTC
2026-04-16T02:07:16.957193612Z [err]  2026-04-16 02:07:16.698 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-16T02:07:16.957196520Z [err]  2026-04-16 02:07:16.771 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-16T02:07:16.957199648Z [err]  2026-04-16 02:07:16.776 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-16T02:07:17.173063866Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-16T02:07:17.632111147Z [err]  2026-04-16 02:07:17.628 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.29 s, system: 0.41 s, elapsed: 0.85 s
2026-04-16T02:07:17.999096030Z [err]  2026-04-16 02:07:17.649 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-16T02:07:17.999099592Z [err]  2026-04-16 02:07:17.654 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-16T02:07:17.999104779Z [err]  2026-04-16 02:07:17.654 UTC [7] LOG:  terminating any other active server processes
2026-04-16T02:07:17.999109480Z [err]  2026-04-16 02:07:17.655 UTC [7] LOG:  shutting down due to startup process failure
2026-04-16T02:07:17.999115993Z [err]  2026-04-16 02:07:17.668 UTC [7] LOG:  database system is shut down
2026-04-16T02:07:27.671995553Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-16T02:07:37.234931843Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-16T02:07:37.763210353Z [inf]  Certificate will not expire
2026-04-16T02:07:37.763214207Z [inf]  
2026-04-16T02:07:37.763217652Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-16T02:07:37.763221459Z [inf]  
2026-04-16T02:07:37.763224402Z [err]  2026-04-16 02:07:28.063 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-16T02:07:37.763227329Z [err]  2026-04-16 02:07:28.063 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-16T02:07:37.763230160Z [err]  2026-04-16 02:07:28.063 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-16T02:07:37.763233458Z [err]  2026-04-16 02:07:28.070 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-16T02:07:37.763236451Z [err]  2026-04-16 02:07:28.077 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-16 02:07:16 UTC
2026-04-16T02:07:37.763240326Z [err]  2026-04-16 02:07:28.077 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-16T02:07:37.763243214Z [err]  2026-04-16 02:07:28.148 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-16T02:07:37.763245948Z [err]  2026-04-16 02:07:28.153 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-16T02:07:37.763248430Z [err]  2026-04-16 02:07:28.957 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.27 s, system: 0.39 s, elapsed: 0.80 s
2026-04-16T02:07:37.763251184Z [err]  2026-04-16 02:07:28.976 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-16T02:07:37.763253789Z [err]  2026-04-16 02:07:28.981 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-16T02:07:37.763257151Z [err]  2026-04-16 02:07:28.981 UTC [7] LOG:  terminating any other active server processes
2026-04-16T02:07:37.763957858Z [err]  2026-04-16 02:07:28.982 UTC [7] LOG:  shutting down due to startup process failure
2026-04-16T02:07:37.763965598Z [err]  2026-04-16 02:07:28.993 UTC [7] LOG:  database system is shut down
2026-04-16T02:07:37.763969974Z [inf]  Certificate will not expire
2026-04-16T02:07:37.763974231Z [inf]  
2026-04-16T02:07:37.763978830Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-16T02:07:37.763982656Z [inf]  
2026-04-16T02:07:37.763986350Z [err]  2026-04-16 02:07:37.481 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-16T02:07:37.763989755Z [err]  2026-04-16 02:07:37.481 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-16T02:07:37.763994527Z [err]  2026-04-16 02:07:37.481 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-16T02:07:37.763998231Z [err]  2026-04-16 02:07:37.488 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-16T02:07:37.764002685Z [err]  2026-04-16 02:07:37.497 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-16 02:07:28 UTC
2026-04-16T02:07:37.764006567Z [err]  2026-04-16 02:07:37.497 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-16T02:07:37.764009970Z [err]  2026-04-16 02:07:37.567 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-16T02:07:37.764013194Z [err]  2026-04-16 02:07:37.572 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-16T02:07:38.361857667Z [err]  2026-04-16 02:07:38.360 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.28 s, system: 0.37 s, elapsed: 0.78 s
2026-04-16T02:07:38.383584675Z [err]  2026-04-16 02:07:38.381 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-16T02:07:38.389019369Z [err]  2026-04-16 02:07:38.386 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-16T02:07:38.389025083Z [err]  2026-04-16 02:07:38.386 UTC [7] LOG:  terminating any other active server processes
2026-04-16T02:07:38.389028865Z [err]  2026-04-16 02:07:38.387 UTC [7] LOG:  shutting down due to startup process failure
2026-04-16T02:07:38.400664906Z [err]  2026-04-16 02:07:38.399 UTC [7] LOG:  database system is shut down
2026-04-16T02:07:45.333437702Z [inf]  Certificate will not expire
2026-04-16T02:07:45.333440873Z [inf]  
2026-04-16T02:07:45.333444076Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-16T02:07:45.333447621Z [inf]  
2026-04-16T02:07:45.333451585Z [err]  2026-04-16 02:07:45.000 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-16T02:07:45.333461353Z [err]  2026-04-16 02:07:45.000 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-16T02:07:45.333464941Z [err]  2026-04-16 02:07:45.000 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-16T02:07:45.333469702Z [err]  2026-04-16 02:07:45.008 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-16T02:07:45.333473470Z [err]  2026-04-16 02:07:45.017 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-16 02:07:37 UTC
2026-04-16T02:07:45.333477444Z [err]  2026-04-16 02:07:45.017 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-16T02:07:45.333481053Z [err]  2026-04-16 02:07:45.089 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-16T02:07:45.333484140Z [err]  2026-04-16 02:07:45.094 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-16T02:07:45.697344260Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-16T02:07:45.922405130Z [err]  2026-04-16 02:07:45.918 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.31 s, system: 0.37 s, elapsed: 0.82 s
2026-04-16T02:07:45.944574966Z [err]  2026-04-16 02:07:45.938 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-16T02:07:45.946296275Z [err]  2026-04-16 02:07:45.944 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-16T02:07:45.946301005Z [err]  2026-04-16 02:07:45.944 UTC [7] LOG:  terminating any other active server processes
2026-04-16T02:07:45.946305523Z [err]  2026-04-16 02:07:45.944 UTC [7] LOG:  shutting down due to startup process failure
2026-04-16T02:07:45.958351915Z [err]  2026-04-16 02:07:45.956 UTC [7] LOG:  database system is shut down
2026-04-16T02:07:54.548289503Z [inf]  Certificate will not expire
2026-04-16T02:07:54.561560119Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-16T02:07:54.589202972Z [inf]  
2026-04-16T02:07:54.589208460Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-16T02:07:54.589212723Z [inf]  
2026-04-16T02:07:54.610776436Z [err]  2026-04-16 02:07:54.601 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-16T02:07:54.610783875Z [err]  2026-04-16 02:07:54.601 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-16T02:07:54.610789548Z [err]  2026-04-16 02:07:54.601 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-16T02:07:54.610793039Z [err]  2026-04-16 02:07:54.608 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-16T02:07:54.622015703Z [err]  2026-04-16 02:07:54.616 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-16 02:07:45 UTC
2026-04-16T02:07:54.622020426Z [err]  2026-04-16 02:07:54.616 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-16T02:07:54.699588160Z [err]  2026-04-16 02:07:54.689 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-16T02:07:54.699592483Z [err]  2026-04-16 02:07:54.694 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-16T02:07:55.556722386Z [err]  2026-04-16 02:07:55.524 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.28 s, system: 0.37 s, elapsed: 0.82 s
2026-04-16T02:07:55.556727135Z [err]  2026-04-16 02:07:55.545 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-16T02:07:55.556729946Z [err]  2026-04-16 02:07:55.550 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-16T02:07:55.556732733Z [err]  2026-04-16 02:07:55.550 UTC [7] LOG:  terminating any other active server processes
2026-04-16T02:07:55.556735429Z [err]  2026-04-16 02:07:55.551 UTC [7] LOG:  shutting down due to startup process failure
2026-04-16T02:07:55.561511662Z [err]  2026-04-16 02:07:55.559 UTC [7] LOG:  database system is shut down
2026-04-16T02:08:02.535375846Z [inf]  Certificate will not expire
2026-04-16T02:08:02.609009428Z [inf]  
2026-04-16T02:08:02.609015549Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-16T02:08:02.609019100Z [inf]  
2026-04-16T02:08:02.609022394Z [err]  2026-04-16 02:08:02.607 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-16T02:08:02.609025971Z [err]  2026-04-16 02:08:02.608 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-16T02:08:02.609029403Z [err]  2026-04-16 02:08:02.608 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-16T02:08:02.620284474Z [err]  2026-04-16 02:08:02.614 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-16T02:08:02.626496059Z [err]  2026-04-16 02:08:02.623 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-16 02:07:54 UTC
2026-04-16T02:08:02.626500600Z [err]  2026-04-16 02:08:02.623 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-16T02:08:02.699800520Z [err]  2026-04-16 02:08:02.694 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-16T02:08:02.699806572Z [err]  2026-04-16 02:08:02.698 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-16T02:08:03.134474447Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-16T02:08:03.507843341Z [err]  2026-04-16 02:08:03.500 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.35 s, system: 0.31 s, elapsed: 0.80 s
2026-04-16T02:08:03.521313340Z [err]  2026-04-16 02:08:03.520 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-16T02:08:03.526426120Z [err]  2026-04-16 02:08:03.525 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-16T02:08:03.526431898Z [err]  2026-04-16 02:08:03.525 UTC [7] LOG:  terminating any other active server processes
2026-04-16T02:08:03.527414448Z [err]  2026-04-16 02:08:03.526 UTC [7] LOG:  shutting down due to startup process failure
2026-04-16T02:08:03.538817141Z [err]  2026-04-16 02:08:03.538 UTC [7] LOG:  database system is shut down
2026-04-16T02:08:13.815337641Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-16T02:08:20.892693977Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-16T02:08:23.389223913Z [inf]  Certificate will not expire
2026-04-16T02:08:23.389229910Z [inf]  
2026-04-16T02:08:23.389233451Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-16T02:08:23.389236843Z [inf]  
2026-04-16T02:08:23.389239836Z [err]  2026-04-16 02:08:13.534 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-16T02:08:23.389243195Z [err]  2026-04-16 02:08:13.534 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-16T02:08:23.389246518Z [err]  2026-04-16 02:08:13.534 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-16T02:08:23.389249891Z [err]  2026-04-16 02:08:13.541 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-16T02:08:23.389253247Z [err]  2026-04-16 02:08:13.552 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-16 02:08:02 UTC
2026-04-16T02:08:23.389257836Z [err]  2026-04-16 02:08:13.552 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-16T02:08:23.389261794Z [err]  2026-04-16 02:08:13.618 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-16T02:08:23.389264921Z [err]  2026-04-16 02:08:13.623 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-16T02:08:23.389267826Z [err]  2026-04-16 02:08:14.410 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.27 s, system: 0.38 s, elapsed: 0.78 s
2026-04-16T02:08:23.389272279Z [err]  2026-04-16 02:08:14.430 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-16T02:08:23.389275488Z [err]  2026-04-16 02:08:14.436 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-16T02:08:23.389278180Z [err]  2026-04-16 02:08:14.436 UTC [7] LOG:  terminating any other active server processes
2026-04-16T02:08:23.390178261Z [err]  2026-04-16 02:08:14.437 UTC [7] LOG:  shutting down due to startup process failure
2026-04-16T02:08:23.390182205Z [err]  2026-04-16 02:08:14.448 UTC [7] LOG:  database system is shut down
2026-04-16T02:08:23.390185438Z [inf]  Certificate will not expire
2026-04-16T02:08:23.390188588Z [inf]  
2026-04-16T02:08:23.390191601Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-16T02:08:23.390194757Z [inf]  
2026-04-16T02:08:23.390198355Z [err]  2026-04-16 02:08:21.192 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-16T02:08:23.390201809Z [err]  2026-04-16 02:08:21.192 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-16T02:08:23.390205142Z [err]  2026-04-16 02:08:21.192 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-16T02:08:23.390208234Z [err]  2026-04-16 02:08:21.199 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-16T02:08:23.390211886Z [err]  2026-04-16 02:08:21.208 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-16 02:08:13 UTC
2026-04-16T02:08:23.390215284Z [err]  2026-04-16 02:08:21.208 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-16T02:08:23.390218522Z [err]  2026-04-16 02:08:21.278 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-16T02:08:23.390221637Z [err]  2026-04-16 02:08:21.283 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-16T02:08:23.390224831Z [err]  2026-04-16 02:08:22.088 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.31 s, system: 0.36 s, elapsed: 0.80 s
2026-04-16T02:08:23.390227840Z [err]  2026-04-16 02:08:22.109 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-16T02:08:23.390847249Z [err]  2026-04-16 02:08:22.114 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-16T02:08:23.390850545Z [err]  2026-04-16 02:08:22.114 UTC [7] LOG:  terminating any other active server processes
2026-04-16T02:08:23.390853478Z [err]  2026-04-16 02:08:22.115 UTC [7] LOG:  shutting down due to startup process failure
2026-04-16T02:08:23.390856389Z [err]  2026-04-16 02:08:22.126 UTC [7] LOG:  database system is shut down
2026-04-17T21:02:06.858595873Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:02:15.602183172Z [inf]  Certificate will not expire
2026-04-17T21:02:15.602184335Z [err]  2026-04-17 21:02:07.369 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:02:15.602192521Z [inf]  
2026-04-17T21:02:15.602195186Z [err]  2026-04-17 21:02:07.374 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:02:15.602197827Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:02:15.602203142Z [inf]  
2026-04-17T21:02:15.602203445Z [err]  2026-04-17 21:02:07.374 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:02:15.602207134Z [err]  2026-04-17 21:02:06.451 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:02:15.602211173Z [err]  2026-04-17 21:02:06.451 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:02:15.602214416Z [err]  2026-04-17 21:02:06.451 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:02:15.602220442Z [err]  2026-04-17 21:02:06.457 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:02:15.602226938Z [err]  2026-04-17 21:02:06.466 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-16 02:08:21 UTC
2026-04-17T21:02:15.602231302Z [err]  2026-04-17 21:02:06.466 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:02:15.602234559Z [err]  2026-04-17 21:02:06.539 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:02:15.602238143Z [err]  2026-04-17 21:02:06.545 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:02:15.602242491Z [err]  2026-04-17 21:02:07.350 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.31 s, system: 0.34 s, elapsed: 0.80 s
2026-04-17T21:02:15.886658962Z [err]  2026-04-17 21:02:07.375 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:02:15.886661802Z [err]  2026-04-17 21:02:07.386 UTC [7] LOG:  database system is shut down
2026-04-17T21:02:19.977712681Z [inf]  Certificate will not expire
2026-04-17T21:02:19.977722518Z [inf]  
2026-04-17T21:02:19.977729125Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:02:19.977734338Z [inf]  
2026-04-17T21:02:19.977740273Z [err]  2026-04-17 21:02:19.899 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:02:19.977746946Z [err]  2026-04-17 21:02:19.899 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:02:19.977754262Z [err]  2026-04-17 21:02:19.899 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:02:19.977760502Z [err]  2026-04-17 21:02:19.906 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:02:19.977766086Z [err]  2026-04-17 21:02:19.915 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:02:06 UTC
2026-04-17T21:02:19.977770941Z [err]  2026-04-17 21:02:19.915 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:02:19.982096647Z [err]  2026-04-17 21:02:19.980 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:02:19.986956238Z [err]  2026-04-17 21:02:19.985 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:02:20.357178820Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:02:20.941634347Z [err]  2026-04-17 21:02:20.788 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.28 s, system: 0.38 s, elapsed: 0.80 s
2026-04-17T21:02:20.941639130Z [err]  2026-04-17 21:02:20.807 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:02:20.941642532Z [err]  2026-04-17 21:02:20.813 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:02:20.941646467Z [err]  2026-04-17 21:02:20.813 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:02:20.941650600Z [err]  2026-04-17 21:02:20.813 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:02:20.941653827Z [err]  2026-04-17 21:02:20.825 UTC [7] LOG:  database system is shut down
2026-04-17T21:02:30.184430074Z [inf]  Certificate will not expire
2026-04-17T21:02:30.237343768Z [inf]  
2026-04-17T21:02:30.237350270Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:02:30.237354111Z [inf]  
2026-04-17T21:02:30.268083219Z [err]  2026-04-17 21:02:30.265 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:02:30.268090017Z [err]  2026-04-17 21:02:30.265 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:02:30.268095193Z [err]  2026-04-17 21:02:30.265 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:02:30.274002788Z [err]  2026-04-17 21:02:30.273 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:02:30.286692162Z [err]  2026-04-17 21:02:30.282 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:02:19 UTC
2026-04-17T21:02:30.286698258Z [err]  2026-04-17 21:02:30.282 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:02:30.360924449Z [err]  2026-04-17 21:02:30.354 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:02:30.362078006Z [err]  2026-04-17 21:02:30.359 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:02:31.174789975Z [err]  2026-04-17 21:02:31.168 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.26 s, system: 0.40 s, elapsed: 0.80 s
2026-04-17T21:02:31.198642749Z [err]  2026-04-17 21:02:31.188 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:02:31.198647743Z [err]  2026-04-17 21:02:31.193 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:02:31.198651460Z [err]  2026-04-17 21:02:31.193 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:02:31.198654354Z [err]  2026-04-17 21:02:31.194 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:02:31.212356231Z [err]  2026-04-17 21:02:31.205 UTC [7] LOG:  database system is shut down
2026-04-17T21:02:31.431215509Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:02:41.448638981Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:02:49.769481308Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:02:50.982115791Z [inf]  Certificate will not expire
2026-04-17T21:02:50.982122759Z [inf]  
2026-04-17T21:02:50.982127276Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:02:50.982132310Z [inf]  
2026-04-17T21:02:50.982136501Z [err]  2026-04-17 21:02:41.242 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:02:50.982140728Z [err]  2026-04-17 21:02:41.242 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:02:50.982144762Z [err]  2026-04-17 21:02:41.242 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:02:50.982148381Z [err]  2026-04-17 21:02:41.249 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:02:50.982152364Z [err]  2026-04-17 21:02:41.259 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:02:30 UTC
2026-04-17T21:02:50.982156090Z [err]  2026-04-17 21:02:41.259 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:02:50.982159485Z [err]  2026-04-17 21:02:41.327 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:02:50.982163022Z [err]  2026-04-17 21:02:41.333 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:02:50.982166875Z [err]  2026-04-17 21:02:42.159 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.35 s, system: 0.33 s, elapsed: 0.82 s
2026-04-17T21:02:50.982171216Z [err]  2026-04-17 21:02:42.177 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:02:50.982174731Z [err]  2026-04-17 21:02:42.183 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:02:50.982178103Z [err]  2026-04-17 21:02:42.183 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:02:50.983825628Z [err]  2026-04-17 21:02:42.184 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:02:50.983828971Z [err]  2026-04-17 21:02:42.194 UTC [7] LOG:  database system is shut down
2026-04-17T21:02:50.983832377Z [inf]  Certificate will not expire
2026-04-17T21:02:50.983835601Z [inf]  
2026-04-17T21:02:50.983838867Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:02:50.983842222Z [inf]  
2026-04-17T21:02:50.983845375Z [err]  2026-04-17 21:02:49.956 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:02:50.983848294Z [err]  2026-04-17 21:02:49.956 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:02:50.983851476Z [err]  2026-04-17 21:02:49.956 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:02:50.983854665Z [err]  2026-04-17 21:02:49.963 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:02:50.983863458Z [err]  2026-04-17 21:02:49.973 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:02:41 UTC
2026-04-17T21:02:50.983866857Z [err]  2026-04-17 21:02:49.973 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:02:50.983870005Z [err]  2026-04-17 21:02:50.046 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:02:50.983872889Z [err]  2026-04-17 21:02:50.053 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:02:50.983876977Z [err]  2026-04-17 21:02:50.856 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.27 s, system: 0.39 s, elapsed: 0.80 s
2026-04-17T21:02:50.983880069Z [err]  2026-04-17 21:02:50.877 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:02:50.985022937Z [err]  2026-04-17 21:02:50.883 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:02:50.985026532Z [err]  2026-04-17 21:02:50.883 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:02:50.985029628Z [err]  2026-04-17 21:02:50.884 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:02:50.985032677Z [err]  2026-04-17 21:02:50.895 UTC [7] LOG:  database system is shut down
2026-04-17T21:03:00.956574723Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:03:09.047321615Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:03:11.000157876Z [inf]  Certificate will not expire
2026-04-17T21:03:11.000165426Z [inf]  
2026-04-17T21:03:11.000169652Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:03:11.000172872Z [inf]  
2026-04-17T21:03:11.000176952Z [err]  2026-04-17 21:03:01.235 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:03:11.000181018Z [err]  2026-04-17 21:03:01.235 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:03:11.000183993Z [err]  2026-04-17 21:03:01.235 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:03:11.000187521Z [err]  2026-04-17 21:03:01.245 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:03:11.000190853Z [err]  2026-04-17 21:03:01.260 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:02:50 UTC
2026-04-17T21:03:11.000194196Z [err]  2026-04-17 21:03:01.260 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:03:11.000197422Z [err]  2026-04-17 21:03:01.332 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:03:11.000203828Z [err]  2026-04-17 21:03:01.335 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:03:11.000207227Z [err]  2026-04-17 21:03:02.139 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.26 s, system: 0.39 s, elapsed: 0.80 s
2026-04-17T21:03:11.000210556Z [err]  2026-04-17 21:03:02.159 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:03:11.000213333Z [err]  2026-04-17 21:03:02.165 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:03:11.000216042Z [err]  2026-04-17 21:03:02.165 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:03:11.000867404Z [err]  2026-04-17 21:03:02.165 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:03:11.000871009Z [err]  2026-04-17 21:03:02.177 UTC [7] LOG:  database system is shut down
2026-04-17T21:03:11.000874293Z [inf]  Certificate will not expire
2026-04-17T21:03:11.000878324Z [inf]  
2026-04-17T21:03:11.000881943Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:03:11.000885040Z [inf]  
2026-04-17T21:03:11.000888165Z [err]  2026-04-17 21:03:09.089 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:03:11.000891553Z [err]  2026-04-17 21:03:09.089 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:03:11.000894718Z [err]  2026-04-17 21:03:09.089 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:03:11.000898421Z [err]  2026-04-17 21:03:09.097 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:03:11.000902083Z [err]  2026-04-17 21:03:09.109 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:03:01 UTC
2026-04-17T21:03:11.000913001Z [err]  2026-04-17 21:03:09.109 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:03:11.000916748Z [err]  2026-04-17 21:03:09.117 UTC [34] FATAL:  the database system is starting up
2026-04-17T21:03:11.000920295Z [err]  2026-04-17 21:03:09.129 UTC [35] FATAL:  the database system is starting up
2026-04-17T21:03:11.000923619Z [err]  2026-04-17 21:03:09.141 UTC [36] FATAL:  the database system is starting up
2026-04-17T21:03:11.000926471Z [err]  2026-04-17 21:03:09.152 UTC [37] FATAL:  the database system is starting up
2026-04-17T21:03:11.000929422Z [err]  2026-04-17 21:03:09.164 UTC [38] FATAL:  the database system is starting up
2026-04-17T21:03:11.001882664Z [err]  2026-04-17 21:03:09.175 UTC [39] FATAL:  the database system is starting up
2026-04-17T21:03:11.001888149Z [err]  2026-04-17 21:03:09.186 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:03:11.001892153Z [err]  2026-04-17 21:03:09.186 UTC [40] FATAL:  the database system is starting up
2026-04-17T21:03:11.001895407Z [err]  2026-04-17 21:03:09.191 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:03:11.001898635Z [err]  2026-04-17 21:03:09.198 UTC [41] FATAL:  the database system is starting up
2026-04-17T21:03:11.001902815Z [err]  2026-04-17 21:03:09.208 UTC [42] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.001905850Z [err]  2026-04-17 21:03:09.208 UTC [42] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.001909272Z [err]  2026-04-17 21:03:09.219 UTC [43] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.001912703Z [err]  2026-04-17 21:03:09.219 UTC [43] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.001916021Z [err]  2026-04-17 21:03:09.230 UTC [44] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.001919337Z [err]  2026-04-17 21:03:09.230 UTC [44] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.001922804Z [err]  2026-04-17 21:03:09.240 UTC [45] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.001926479Z [err]  2026-04-17 21:03:09.240 UTC [45] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.001929904Z [err]  2026-04-17 21:03:09.251 UTC [46] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.001933489Z [err]  2026-04-17 21:03:09.251 UTC [46] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.001938324Z [err]  2026-04-17 21:03:09.262 UTC [47] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.002609135Z [err]  2026-04-17 21:03:09.262 UTC [47] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.002613506Z [err]  2026-04-17 21:03:09.272 UTC [48] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.002617374Z [err]  2026-04-17 21:03:09.272 UTC [48] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.002621224Z [err]  2026-04-17 21:03:09.283 UTC [49] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.002625429Z [err]  2026-04-17 21:03:09.283 UTC [49] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.002629975Z [err]  2026-04-17 21:03:09.295 UTC [50] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.002633667Z [err]  2026-04-17 21:03:09.295 UTC [50] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.002637342Z [err]  2026-04-17 21:03:09.306 UTC [51] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.002640424Z [err]  2026-04-17 21:03:09.306 UTC [51] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.002643705Z [err]  2026-04-17 21:03:09.317 UTC [52] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.002646853Z [err]  2026-04-17 21:03:09.317 UTC [52] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.002650726Z [err]  2026-04-17 21:03:09.330 UTC [53] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.002653976Z [err]  2026-04-17 21:03:09.330 UTC [53] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.002657339Z [err]  2026-04-17 21:03:09.342 UTC [54] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.002660398Z [err]  2026-04-17 21:03:09.342 UTC [54] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.003451844Z [err]  2026-04-17 21:03:09.354 UTC [55] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.003457075Z [err]  2026-04-17 21:03:09.354 UTC [55] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.003460969Z [err]  2026-04-17 21:03:09.370 UTC [56] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.003464967Z [err]  2026-04-17 21:03:09.370 UTC [56] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.003468656Z [err]  2026-04-17 21:03:09.381 UTC [57] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.003471713Z [err]  2026-04-17 21:03:09.381 UTC [57] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.003474939Z [err]  2026-04-17 21:03:09.392 UTC [58] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.003478173Z [err]  2026-04-17 21:03:09.392 UTC [58] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.003481475Z [err]  2026-04-17 21:03:09.404 UTC [59] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.003485322Z [err]  2026-04-17 21:03:09.404 UTC [59] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.003488870Z [err]  2026-04-17 21:03:09.415 UTC [60] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.003492093Z [err]  2026-04-17 21:03:09.415 UTC [60] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.003495496Z [err]  2026-04-17 21:03:09.427 UTC [61] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.003498984Z [err]  2026-04-17 21:03:09.427 UTC [61] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.003503071Z [err]  2026-04-17 21:03:09.438 UTC [62] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.004252734Z [err]  2026-04-17 21:03:09.525 UTC [69] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.004257003Z [err]  2026-04-17 21:03:09.438 UTC [62] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.004261961Z [err]  2026-04-17 21:03:09.455 UTC [63] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.004264989Z [err]  2026-04-17 21:03:09.455 UTC [63] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.004268375Z [err]  2026-04-17 21:03:09.468 UTC [64] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.004271482Z [err]  2026-04-17 21:03:09.468 UTC [64] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.004274692Z [err]  2026-04-17 21:03:09.479 UTC [65] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.004277761Z [err]  2026-04-17 21:03:09.479 UTC [65] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.004280681Z [err]  2026-04-17 21:03:09.490 UTC [66] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.004284138Z [err]  2026-04-17 21:03:09.490 UTC [66] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.004287046Z [err]  2026-04-17 21:03:09.501 UTC [67] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.004289982Z [err]  2026-04-17 21:03:09.501 UTC [67] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.004293046Z [err]  2026-04-17 21:03:09.513 UTC [68] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.004296059Z [err]  2026-04-17 21:03:09.513 UTC [68] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.004298884Z [err]  2026-04-17 21:03:09.525 UTC [69] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005106846Z [err]  2026-04-17 21:03:09.536 UTC [70] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005110220Z [err]  2026-04-17 21:03:09.536 UTC [70] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005113455Z [err]  2026-04-17 21:03:09.547 UTC [71] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005116583Z [err]  2026-04-17 21:03:09.547 UTC [71] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005120176Z [err]  2026-04-17 21:03:09.558 UTC [72] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005123742Z [err]  2026-04-17 21:03:09.558 UTC [72] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005127502Z [err]  2026-04-17 21:03:09.570 UTC [73] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005134523Z [err]  2026-04-17 21:03:09.570 UTC [73] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005137810Z [err]  2026-04-17 21:03:09.582 UTC [74] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005140809Z [err]  2026-04-17 21:03:09.582 UTC [74] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005143776Z [err]  2026-04-17 21:03:09.593 UTC [75] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005146716Z [err]  2026-04-17 21:03:09.593 UTC [75] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005149833Z [err]  2026-04-17 21:03:09.604 UTC [76] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005152990Z [err]  2026-04-17 21:03:09.604 UTC [76] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005155934Z [err]  2026-04-17 21:03:09.615 UTC [77] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005921918Z [err]  2026-04-17 21:03:09.615 UTC [77] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005925418Z [err]  2026-04-17 21:03:09.625 UTC [78] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005930450Z [err]  2026-04-17 21:03:09.625 UTC [78] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005934038Z [err]  2026-04-17 21:03:09.635 UTC [79] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005937119Z [err]  2026-04-17 21:03:09.635 UTC [79] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005940113Z [err]  2026-04-17 21:03:09.646 UTC [80] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005943119Z [err]  2026-04-17 21:03:09.646 UTC [80] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005945842Z [err]  2026-04-17 21:03:09.657 UTC [81] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005948510Z [err]  2026-04-17 21:03:09.657 UTC [81] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005951407Z [err]  2026-04-17 21:03:09.667 UTC [82] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005954466Z [err]  2026-04-17 21:03:09.667 UTC [82] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005957255Z [err]  2026-04-17 21:03:09.678 UTC [83] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005959990Z [err]  2026-04-17 21:03:09.678 UTC [83] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.005967188Z [err]  2026-04-17 21:03:09.689 UTC [84] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.005971769Z [err]  2026-04-17 21:03:09.689 UTC [84] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.006903951Z [err]  2026-04-17 21:03:09.763 UTC [91] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.006908219Z [err]  2026-04-17 21:03:09.775 UTC [92] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.006910744Z [err]  2026-04-17 21:03:09.699 UTC [85] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.006916854Z [err]  2026-04-17 21:03:09.699 UTC [85] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.006920191Z [err]  2026-04-17 21:03:09.710 UTC [86] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.006923391Z [err]  2026-04-17 21:03:09.710 UTC [86] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.006926436Z [err]  2026-04-17 21:03:09.722 UTC [87] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.006929466Z [err]  2026-04-17 21:03:09.722 UTC [87] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.006932751Z [err]  2026-04-17 21:03:09.732 UTC [88] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.006935815Z [err]  2026-04-17 21:03:09.732 UTC [88] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.006938613Z [err]  2026-04-17 21:03:09.743 UTC [89] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.006942370Z [err]  2026-04-17 21:03:09.743 UTC [89] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.006945672Z [err]  2026-04-17 21:03:09.753 UTC [90] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.006948561Z [err]  2026-04-17 21:03:09.753 UTC [90] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.006951443Z [err]  2026-04-17 21:03:09.763 UTC [91] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008095266Z [err]  2026-04-17 21:03:09.775 UTC [92] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008104609Z [err]  2026-04-17 21:03:09.785 UTC [93] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008108958Z [err]  2026-04-17 21:03:09.785 UTC [93] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008112913Z [err]  2026-04-17 21:03:09.796 UTC [94] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008116878Z [err]  2026-04-17 21:03:09.796 UTC [94] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008121237Z [err]  2026-04-17 21:03:09.807 UTC [95] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008125013Z [err]  2026-04-17 21:03:09.807 UTC [95] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008129228Z [err]  2026-04-17 21:03:09.818 UTC [96] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008132910Z [err]  2026-04-17 21:03:09.818 UTC [96] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008137977Z [err]  2026-04-17 21:03:09.829 UTC [97] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008141553Z [err]  2026-04-17 21:03:09.829 UTC [97] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008145044Z [err]  2026-04-17 21:03:09.840 UTC [98] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008148534Z [err]  2026-04-17 21:03:09.840 UTC [98] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008151902Z [err]  2026-04-17 21:03:09.850 UTC [99] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008155385Z [err]  2026-04-17 21:03:09.850 UTC [99] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008775899Z [err]  2026-04-17 21:03:09.930 UTC [106] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008776256Z [err]  2026-04-17 21:03:09.862 UTC [100] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008780899Z [err]  2026-04-17 21:03:09.941 UTC [107] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008782274Z [err]  2026-04-17 21:03:09.862 UTC [100] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008786262Z [err]  2026-04-17 21:03:09.875 UTC [101] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008789356Z [err]  2026-04-17 21:03:09.875 UTC [101] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008793751Z [err]  2026-04-17 21:03:09.908 UTC [104] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008793771Z [err]  2026-04-17 21:03:09.886 UTC [102] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008797206Z [err]  2026-04-17 21:03:09.886 UTC [102] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008799588Z [err]  2026-04-17 21:03:09.920 UTC [105] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008802345Z [err]  2026-04-17 21:03:09.897 UTC [103] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008806684Z [err]  2026-04-17 21:03:09.920 UTC [105] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008807817Z [err]  2026-04-17 21:03:09.897 UTC [103] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.008813244Z [err]  2026-04-17 21:03:09.930 UTC [106] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.008813326Z [err]  2026-04-17 21:03:09.908 UTC [104] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.009612556Z [err]  2026-04-17 21:03:09.941 UTC [107] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.009617116Z [err]  2026-04-17 21:03:09.953 UTC [108] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.009620822Z [err]  2026-04-17 21:03:09.953 UTC [108] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.009623880Z [err]  2026-04-17 21:03:09.964 UTC [109] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.009627303Z [err]  2026-04-17 21:03:09.964 UTC [109] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.009630658Z [err]  2026-04-17 21:03:09.976 UTC [110] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.009633661Z [err]  2026-04-17 21:03:09.976 UTC [110] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.009639420Z [err]  2026-04-17 21:03:09.987 UTC [111] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.009642841Z [err]  2026-04-17 21:03:09.987 UTC [111] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.009646236Z [err]  2026-04-17 21:03:09.999 UTC [112] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.009649481Z [err]  2026-04-17 21:03:09.999 UTC [112] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.009652678Z [err]  2026-04-17 21:03:10.009 UTC [113] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.009655765Z [err]  2026-04-17 21:03:10.009 UTC [113] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.009659011Z [err]  2026-04-17 21:03:10.014 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.31 s, system: 0.34 s, elapsed: 0.82 s
2026-04-17T21:03:11.009663872Z [err]  2026-04-17 21:03:10.020 UTC [114] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.010357721Z [err]  2026-04-17 21:03:10.020 UTC [114] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.010361282Z [err]  2026-04-17 21:03:10.030 UTC [115] FATAL:  the database system is not yet accepting connections
2026-04-17T21:03:11.010364056Z [err]  2026-04-17 21:03:10.030 UTC [115] DETAIL:  Consistent recovery state has not been yet reached.
2026-04-17T21:03:11.010366718Z [err]  2026-04-17 21:03:10.035 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:03:11.010369404Z [err]  2026-04-17 21:03:10.040 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:03:11.010372254Z [err]  2026-04-17 21:03:10.040 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:03:11.010377504Z [err]  2026-04-17 21:03:10.040 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:03:11.010380752Z [err]  2026-04-17 21:03:10.051 UTC [7] LOG:  database system is shut down
2026-04-17T21:03:23.317705976Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:03:30.714758517Z [inf]  Certificate will not expire
2026-04-17T21:03:30.714767757Z [inf]  
2026-04-17T21:03:30.714772405Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:03:30.714776177Z [inf]  
2026-04-17T21:03:30.714780063Z [err]  2026-04-17 21:03:22.691 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:03:30.714784645Z [err]  2026-04-17 21:03:22.691 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:03:30.714788281Z [err]  2026-04-17 21:03:22.691 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:03:30.714792126Z [err]  2026-04-17 21:03:22.699 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:03:30.714795952Z [err]  2026-04-17 21:03:22.708 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:03:09 UTC
2026-04-17T21:03:30.714799763Z [err]  2026-04-17 21:03:22.708 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:03:30.714803322Z [err]  2026-04-17 21:03:22.781 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:03:30.714806951Z [err]  2026-04-17 21:03:22.786 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:03:30.714810969Z [err]  2026-04-17 21:03:23.572 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.28 s, system: 0.36 s, elapsed: 0.78 s
2026-04-17T21:03:30.714814583Z [err]  2026-04-17 21:03:23.592 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:03:30.714818280Z [err]  2026-04-17 21:03:23.597 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:03:30.714821678Z [err]  2026-04-17 21:03:23.597 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:03:30.715797600Z [err]  2026-04-17 21:03:23.598 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:03:30.715805880Z [err]  2026-04-17 21:03:23.609 UTC [7] LOG:  database system is shut down
2026-04-17T21:03:34.339312145Z [inf]  Certificate will not expire
2026-04-17T21:03:34.339315840Z [inf]  
2026-04-17T21:03:34.339320382Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:03:34.339323742Z [inf]  
2026-04-17T21:03:34.339327053Z [err]  2026-04-17 21:03:34.295 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:03:34.339330854Z [err]  2026-04-17 21:03:34.295 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:03:34.339334243Z [err]  2026-04-17 21:03:34.295 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:03:34.339337296Z [err]  2026-04-17 21:03:34.301 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:03:34.339340284Z [err]  2026-04-17 21:03:34.310 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:03:22 UTC
2026-04-17T21:03:34.339343163Z [err]  2026-04-17 21:03:34.310 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:03:34.414533256Z [err]  2026-04-17 21:03:34.382 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:03:34.414537624Z [err]  2026-04-17 21:03:34.387 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:03:35.005604327Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:03:35.364747640Z [err]  2026-04-17 21:03:35.193 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.26 s, system: 0.40 s, elapsed: 0.80 s
2026-04-17T21:03:35.364751020Z [err]  2026-04-17 21:03:35.213 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:03:35.364754453Z [err]  2026-04-17 21:03:35.219 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:03:35.364757650Z [err]  2026-04-17 21:03:35.219 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:03:35.364760520Z [err]  2026-04-17 21:03:35.219 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:03:35.364763379Z [err]  2026-04-17 21:03:35.230 UTC [7] LOG:  database system is shut down
2026-04-17T21:03:42.043943621Z [inf]  Certificate will not expire
2026-04-17T21:03:42.104321315Z [inf]  
2026-04-17T21:03:42.104326459Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:03:42.104330431Z [inf]  
2026-04-17T21:03:42.145303610Z [err]  2026-04-17 21:03:42.125 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:03:42.145311608Z [err]  2026-04-17 21:03:42.126 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:03:42.145317449Z [err]  2026-04-17 21:03:42.126 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:03:42.145321642Z [err]  2026-04-17 21:03:42.132 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:03:42.145327586Z [err]  2026-04-17 21:03:42.142 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:03:34 UTC
2026-04-17T21:03:42.145332829Z [err]  2026-04-17 21:03:42.142 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:03:42.451989139Z [err]  2026-04-17 21:03:42.214 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:03:42.451993587Z [err]  2026-04-17 21:03:42.219 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:03:42.669471959Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:03:43.053154399Z [err]  2026-04-17 21:03:43.030 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.27 s, system: 0.39 s, elapsed: 0.81 s
2026-04-17T21:03:43.053161880Z [err]  2026-04-17 21:03:43.051 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:03:43.064615647Z [err]  2026-04-17 21:03:43.057 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:03:43.064619941Z [err]  2026-04-17 21:03:43.057 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:03:43.064624161Z [err]  2026-04-17 21:03:43.058 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:03:43.076212080Z [err]  2026-04-17 21:03:43.069 UTC [7] LOG:  database system is shut down
2026-04-17T21:03:52.687982941Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:03:52.713133812Z [inf]  Certificate will not expire
2026-04-17T21:03:52.756519454Z [inf]  
2026-04-17T21:03:52.756526368Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:03:52.756530431Z [inf]  
2026-04-17T21:03:52.778600913Z [err]  2026-04-17 21:03:52.776 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:03:52.778605904Z [err]  2026-04-17 21:03:52.776 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:03:52.778609355Z [err]  2026-04-17 21:03:52.776 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:03:52.789364372Z [err]  2026-04-17 21:03:52.783 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:03:52.793642400Z [err]  2026-04-17 21:03:52.792 UTC [32] LOG:  database system was interrupted while in recovery at 2026-04-17 21:03:42 UTC
2026-04-17T21:03:52.793646957Z [err]  2026-04-17 21:03:52.792 UTC [32] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:03:52.878817171Z [err]  2026-04-17 21:03:52.875 UTC [32] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:03:52.883719676Z [err]  2026-04-17 21:03:52.881 UTC [32] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:03:53.696657542Z [err]  2026-04-17 21:03:53.692 UTC [32] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.33 s, system: 0.32 s, elapsed: 0.81 s
2026-04-17T21:03:53.719207185Z [err]  2026-04-17 21:03:53.713 UTC [32] FATAL:  could not write to file "pg_wal/xlogtemp.32": No space left on device
2026-04-17T21:03:53.720510717Z [err]  2026-04-17 21:03:53.719 UTC [7] LOG:  startup process (PID 32) exited with exit code 1
2026-04-17T21:03:53.720516811Z [err]  2026-04-17 21:03:53.719 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:03:53.721272724Z [err]  2026-04-17 21:03:53.720 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:03:53.734434248Z [err]  2026-04-17 21:03:53.731 UTC [7] LOG:  database system is shut down
2026-04-17T21:19:59.810450272Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:20:07.823287741Z [inf]  Certificate will not expire
2026-04-17T21:20:07.823291357Z [inf]  
2026-04-17T21:20:07.823295092Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:20:07.823298744Z [inf]  
2026-04-17T21:20:07.823302357Z [err]  2026-04-17 21:20:00.000 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:20:07.823305588Z [err]  2026-04-17 21:20:00.000 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:20:07.823309118Z [err]  2026-04-17 21:20:00.000 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:20:07.823312786Z [err]  2026-04-17 21:20:00.007 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:20:07.823316189Z [err]  2026-04-17 21:20:00.015 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:03:52 UTC
2026-04-17T21:20:07.823319229Z [err]  2026-04-17 21:20:00.015 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:20:07.823322368Z [err]  2026-04-17 21:20:00.086 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:20:07.823325298Z [err]  2026-04-17 21:20:00.091 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:20:07.823328150Z [err]  2026-04-17 21:20:00.888 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.25 s, system: 0.40 s, elapsed: 0.79 s
2026-04-17T21:20:07.823331100Z [err]  2026-04-17 21:20:00.910 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:20:07.823333861Z [err]  2026-04-17 21:20:00.915 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:20:07.823337091Z [err]  2026-04-17 21:20:00.915 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:20:07.823408660Z [err]  2026-04-17 21:20:00.916 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:20:07.823412110Z [err]  2026-04-17 21:20:00.928 UTC [7] LOG:  database system is shut down
2026-04-17T21:20:07.874520958Z [inf]  Certificate will not expire
2026-04-17T21:20:07.920932563Z [inf]  
2026-04-17T21:20:07.920937241Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:20:07.920940233Z [inf]  
2026-04-17T21:20:07.954058081Z [err]  2026-04-17 21:20:07.949 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:20:07.954062577Z [err]  2026-04-17 21:20:07.949 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:20:07.954065390Z [err]  2026-04-17 21:20:07.949 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:20:07.959839213Z [err]  2026-04-17 21:20:07.956 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:20:07.971303700Z [err]  2026-04-17 21:20:07.967 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:20:00 UTC
2026-04-17T21:20:07.971308726Z [err]  2026-04-17 21:20:07.967 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:20:08.048937758Z [err]  2026-04-17 21:20:08.042 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:20:08.049633679Z [err]  2026-04-17 21:20:08.047 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:20:08.349661995Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:20:08.841255769Z [err]  2026-04-17 21:20:08.839 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.32 s, system: 0.32 s, elapsed: 0.79 s
2026-04-17T21:20:08.864443570Z [err]  2026-04-17 21:20:08.859 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:20:08.869928524Z [err]  2026-04-17 21:20:08.864 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:20:08.869934166Z [err]  2026-04-17 21:20:08.864 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:20:08.869938280Z [err]  2026-04-17 21:20:08.865 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:20:08.882480759Z [err]  2026-04-17 21:20:08.876 UTC [7] LOG:  database system is shut down
2026-04-17T21:20:21.149665541Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:20:28.711552223Z [inf]  Certificate will not expire
2026-04-17T21:20:28.711560963Z [inf]  
2026-04-17T21:20:28.711564848Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:20:28.711568425Z [inf]  
2026-04-17T21:20:28.711571599Z [err]  2026-04-17 21:20:21.188 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:20:28.711575206Z [err]  2026-04-17 21:20:21.188 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:20:28.711580802Z [err]  2026-04-17 21:20:21.188 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:20:28.711584468Z [err]  2026-04-17 21:20:21.195 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:20:28.711589519Z [err]  2026-04-17 21:20:21.205 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:20:08 UTC
2026-04-17T21:20:28.711592969Z [err]  2026-04-17 21:20:21.205 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:20:28.711597103Z [err]  2026-04-17 21:20:21.276 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:20:28.711600888Z [err]  2026-04-17 21:20:21.282 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:20:28.711604214Z [err]  2026-04-17 21:20:22.092 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.28 s, system: 0.38 s, elapsed: 0.81 s
2026-04-17T21:20:28.711608943Z [err]  2026-04-17 21:20:22.110 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:20:28.711612414Z [err]  2026-04-17 21:20:22.116 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:20:28.711615854Z [err]  2026-04-17 21:20:22.116 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:20:28.712237342Z [err]  2026-04-17 21:20:22.116 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:20:28.712242330Z [err]  2026-04-17 21:20:22.128 UTC [7] LOG:  database system is shut down
2026-04-17T21:20:32.329387938Z [inf]  Certificate will not expire
2026-04-17T21:20:32.371106656Z [inf]  
2026-04-17T21:20:32.371111703Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:20:32.371115225Z [inf]  
2026-04-17T21:20:32.386809961Z [err]  2026-04-17 21:20:32.380 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:20:32.386815070Z [err]  2026-04-17 21:20:32.380 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:20:32.386818804Z [err]  2026-04-17 21:20:32.380 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:20:32.388329733Z [err]  2026-04-17 21:20:32.387 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:20:32.400898271Z [err]  2026-04-17 21:20:32.396 UTC [32] LOG:  database system was interrupted while in recovery at 2026-04-17 21:20:21 UTC
2026-04-17T21:20:32.400903938Z [err]  2026-04-17 21:20:32.396 UTC [32] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:20:32.469518017Z [err]  2026-04-17 21:20:32.468 UTC [32] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:20:32.475864197Z [err]  2026-04-17 21:20:32.472 UTC [32] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:20:32.796739350Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:20:33.281444033Z [err]  2026-04-17 21:20:33.265 UTC [32] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.28 s, system: 0.37 s, elapsed: 0.79 s
2026-04-17T21:20:33.286995950Z [err]  2026-04-17 21:20:33.286 UTC [32] FATAL:  could not write to file "pg_wal/xlogtemp.32": No space left on device
2026-04-17T21:20:33.293774384Z [err]  2026-04-17 21:20:33.291 UTC [7] LOG:  startup process (PID 32) exited with exit code 1
2026-04-17T21:20:33.293779011Z [err]  2026-04-17 21:20:33.291 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:20:33.293783076Z [err]  2026-04-17 21:20:33.292 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:20:33.306337285Z [err]  2026-04-17 21:20:33.304 UTC [7] LOG:  database system is shut down
2026-04-17T21:20:43.538716016Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:20:52.150531209Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:20:53.137551769Z [inf]  Certificate will not expire
2026-04-17T21:20:53.137558481Z [inf]  
2026-04-17T21:20:53.137563266Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:20:53.137567416Z [inf]  
2026-04-17T21:20:53.137573087Z [err]  2026-04-17 21:20:43.670 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:20:53.137577477Z [err]  2026-04-17 21:20:43.670 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:20:53.137581437Z [err]  2026-04-17 21:20:43.670 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:20:53.137584926Z [err]  2026-04-17 21:20:43.677 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:20:53.137587940Z [err]  2026-04-17 21:20:43.686 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:20:32 UTC
2026-04-17T21:20:53.137591304Z [err]  2026-04-17 21:20:43.686 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:20:53.137594291Z [err]  2026-04-17 21:20:43.755 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:20:53.137597201Z [err]  2026-04-17 21:20:43.760 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:20:53.137600138Z [err]  2026-04-17 21:20:44.569 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.27 s, system: 0.40 s, elapsed: 0.80 s
2026-04-17T21:20:53.137603085Z [err]  2026-04-17 21:20:44.589 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:20:53.137605975Z [err]  2026-04-17 21:20:44.595 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:20:53.137609132Z [err]  2026-04-17 21:20:44.595 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:20:53.138178178Z [err]  2026-04-17 21:20:44.595 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:20:53.138184541Z [err]  2026-04-17 21:20:44.606 UTC [7] LOG:  database system is shut down
2026-04-17T21:20:53.138188158Z [inf]  Certificate will not expire
2026-04-17T21:20:53.138191825Z [inf]  
2026-04-17T21:20:53.138195131Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:20:53.138200256Z [inf]  
2026-04-17T21:20:53.138204733Z [err]  2026-04-17 21:20:51.832 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:20:53.138208052Z [err]  2026-04-17 21:20:51.832 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:20:53.138212285Z [err]  2026-04-17 21:20:51.832 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:20:53.138216387Z [err]  2026-04-17 21:20:51.840 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:20:53.138219786Z [err]  2026-04-17 21:20:51.850 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:20:43 UTC
2026-04-17T21:20:53.138223690Z [err]  2026-04-17 21:20:51.850 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:20:53.138227345Z [err]  2026-04-17 21:20:51.925 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:20:53.138230613Z [err]  2026-04-17 21:20:51.930 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:20:53.138234695Z [err]  2026-04-17 21:20:52.735 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.29 s, system: 0.36 s, elapsed: 0.80 s
2026-04-17T21:20:53.138239119Z [err]  2026-04-17 21:20:52.756 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:20:53.138571753Z [err]  2026-04-17 21:20:52.761 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:20:53.138576567Z [err]  2026-04-17 21:20:52.761 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:20:53.138579428Z [err]  2026-04-17 21:20:52.762 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:20:53.138582671Z [err]  2026-04-17 21:20:52.774 UTC [7] LOG:  database system is shut down
2026-04-17T21:20:59.829832265Z [inf]  Certificate will not expire
2026-04-17T21:20:59.875706282Z [inf]  
2026-04-17T21:20:59.875710981Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:20:59.875714604Z [inf]  
2026-04-17T21:20:59.906254988Z [err]  2026-04-17 21:20:59.901 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:20:59.906260042Z [err]  2026-04-17 21:20:59.902 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:20:59.906263271Z [err]  2026-04-17 21:20:59.902 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:20:59.911599077Z [err]  2026-04-17 21:20:59.908 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:20:59.925472913Z [err]  2026-04-17 21:20:59.917 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:20:51 UTC
2026-04-17T21:20:59.925479750Z [err]  2026-04-17 21:20:59.917 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:21:00.001755106Z [err]  2026-04-17 21:20:59.991 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:21:00.001762947Z [err]  2026-04-17 21:20:59.996 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:21:00.481413308Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:21:00.870043907Z [err]  2026-04-17 21:21:00.853 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.32 s, system: 0.38 s, elapsed: 0.85 s
2026-04-17T21:21:00.876189242Z [err]  2026-04-17 21:21:00.874 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:21:00.883806896Z [err]  2026-04-17 21:21:00.880 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:21:00.883812619Z [err]  2026-04-17 21:21:00.880 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:21:00.883815972Z [err]  2026-04-17 21:21:00.881 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:21:00.896402423Z [err]  2026-04-17 21:21:00.893 UTC [7] LOG:  database system is shut down
2026-04-17T21:21:17.576075532Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:21:20.906071822Z [inf]  Certificate will not expire
2026-04-17T21:21:20.906075921Z [inf]  
2026-04-17T21:21:20.906079863Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:21:20.906083560Z [inf]  
2026-04-17T21:21:20.906087122Z [err]  2026-04-17 21:21:17.162 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:21:20.906090282Z [err]  2026-04-17 21:21:17.163 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:21:20.906093574Z [err]  2026-04-17 21:21:17.163 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:21:20.906096874Z [err]  2026-04-17 21:21:17.170 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:21:20.906100209Z [err]  2026-04-17 21:21:17.178 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:20:59 UTC
2026-04-17T21:21:20.906104884Z [err]  2026-04-17 21:21:17.178 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:21:20.906108251Z [err]  2026-04-17 21:21:17.243 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:21:20.906111686Z [err]  2026-04-17 21:21:17.248 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:21:20.906115230Z [err]  2026-04-17 21:21:18.072 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.33 s, system: 0.34 s, elapsed: 0.82 s
2026-04-17T21:21:20.906118405Z [err]  2026-04-17 21:21:18.091 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:21:20.906121619Z [err]  2026-04-17 21:21:18.097 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:21:20.906124661Z [err]  2026-04-17 21:21:18.097 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:21:20.906180008Z [err]  2026-04-17 21:21:18.097 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:21:20.906185596Z [err]  2026-04-17 21:21:18.108 UTC [7] LOG:  database system is shut down
2026-04-17T21:21:25.280815761Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:21:25.421082959Z [inf]  Certificate will not expire
2026-04-17T21:21:25.465810378Z [inf]  
2026-04-17T21:21:25.465814337Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:21:25.465817386Z [inf]  
2026-04-17T21:21:25.502007472Z [err]  2026-04-17 21:21:25.494 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:21:25.502016070Z [err]  2026-04-17 21:21:25.494 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:21:25.502020162Z [err]  2026-04-17 21:21:25.494 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:21:25.504281799Z [err]  2026-04-17 21:21:25.502 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:21:25.516244343Z [err]  2026-04-17 21:21:25.511 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:21:17 UTC
2026-04-17T21:21:25.516248619Z [err]  2026-04-17 21:21:25.511 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:21:25.581029861Z [err]  2026-04-17 21:21:25.578 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:21:25.586030616Z [err]  2026-04-17 21:21:25.582 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:21:26.454808982Z [err]  2026-04-17 21:21:26.387 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.28 s, system: 0.38 s, elapsed: 0.80 s
2026-04-17T21:21:26.454814487Z [err]  2026-04-17 21:21:26.406 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:21:26.454818044Z [err]  2026-04-17 21:21:26.412 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:21:26.454821679Z [err]  2026-04-17 21:21:26.412 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:21:26.454824982Z [err]  2026-04-17 21:21:26.413 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:21:26.454828350Z [err]  2026-04-17 21:21:26.425 UTC [7] LOG:  database system is shut down
2026-04-17T21:21:37.374588946Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:21:46.098533155Z [inf]  Mounting volume on: /var/lib/containers/railwayapp/bind-mounts/14bc4a4e-de96-4538-845f-03059a8dad4f/vol_0qj4njod9eky8zrv
2026-04-17T21:21:46.436512102Z [err]  2026-04-17 21:21:37.166 UTC [33] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:21:46.436517956Z [err]  2026-04-17 21:21:37.171 UTC [33] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:21:46.436522208Z [err]  2026-04-17 21:21:37.988 UTC [33] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.29 s, system: 0.37 s, elapsed: 0.81 s
2026-04-17T21:21:46.436526860Z [err]  2026-04-17 21:21:38.007 UTC [33] FATAL:  could not write to file "pg_wal/xlogtemp.33": No space left on device
2026-04-17T21:21:46.436532840Z [err]  2026-04-17 21:21:38.013 UTC [7] LOG:  startup process (PID 33) exited with exit code 1
2026-04-17T21:21:46.436532963Z [inf]  Certificate will not expire
2026-04-17T21:21:46.436539129Z [inf]  
2026-04-17T21:21:46.436541321Z [err]  2026-04-17 21:21:38.013 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:21:46.436544029Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:21:46.436547597Z [inf]  
2026-04-17T21:21:46.436550233Z [err]  2026-04-17 21:21:37.081 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:21:46.436552978Z [err]  2026-04-17 21:21:37.081 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:21:46.436555595Z [err]  2026-04-17 21:21:37.081 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:21:46.436558319Z [err]  2026-04-17 21:21:37.088 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:21:46.436561051Z [err]  2026-04-17 21:21:37.097 UTC [33] LOG:  database system was interrupted while in recovery at 2026-04-17 21:21:25 UTC
2026-04-17T21:21:46.436564301Z [err]  2026-04-17 21:21:37.097 UTC [33] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:21:46.437170955Z [err]  2026-04-17 21:21:46.267 UTC [32] FATAL:  could not write to file "pg_wal/xlogtemp.32": No space left on device
2026-04-17T21:21:46.437196394Z [err]  2026-04-17 21:21:38.013 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:21:46.437202181Z [err]  2026-04-17 21:21:38.025 UTC [7] LOG:  database system is shut down
2026-04-17T21:21:46.437205674Z [inf]  Certificate will not expire
2026-04-17T21:21:46.437208577Z [inf]  
2026-04-17T21:21:46.437212112Z [inf]  PostgreSQL Database directory appears to contain a database; Skipping initialization
2026-04-17T21:21:46.437215147Z [inf]  
2026-04-17T21:21:46.437218021Z [err]  2026-04-17 21:21:45.363 UTC [7] LOG:  starting PostgreSQL 18.3 (Debian 18.3-1.pgdg13+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit
2026-04-17T21:21:46.437220543Z [err]  2026-04-17 21:21:45.363 UTC [7] LOG:  listening on IPv4 address "0.0.0.0", port 5432
2026-04-17T21:21:46.437223804Z [err]  2026-04-17 21:21:45.363 UTC [7] LOG:  listening on IPv6 address "::", port 5432
2026-04-17T21:21:46.437227062Z [err]  2026-04-17 21:21:45.370 UTC [7] LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
2026-04-17T21:21:46.437229752Z [err]  2026-04-17 21:21:45.378 UTC [32] LOG:  database system was interrupted while in recovery at 2026-04-17 21:21:37 UTC
2026-04-17T21:21:46.437232381Z [err]  2026-04-17 21:21:45.378 UTC [32] HINT:  This probably means that some data is corrupted and you will have to use the last backup for recovery.
2026-04-17T21:21:46.437235173Z [err]  2026-04-17 21:21:45.450 UTC [32] LOG:  database system was not properly shut down; automatic recovery in progress
2026-04-17T21:21:46.437238075Z [err]  2026-04-17 21:21:45.455 UTC [32] LOG:  redo starts at D/66AB8DA8
2026-04-17T21:21:46.437240951Z [err]  2026-04-17 21:21:46.248 UTC [32] LOG:  redo done at D/7FFFFFB8 system usage: CPU: user: 0.30 s, system: 0.34 s, elapsed: 0.79 s
2026-04-17T21:21:46.437791630Z [err]  2026-04-17 21:21:46.272 UTC [7] LOG:  startup process (PID 32) exited with exit code 1
2026-04-17T21:21:46.437796241Z [err]  2026-04-17 21:21:46.272 UTC [7] LOG:  terminating any other active server processes
2026-04-17T21:21:46.437799517Z [err]  2026-04-17 21:21:46.273 UTC [7] LOG:  shutting down due to startup process failure
2026-04-17T21:21:46.437802864Z [err]  2026-04-17 21:21:46.284 UTC [7] LOG:  database system is shut down