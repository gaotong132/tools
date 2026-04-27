"""HTML模板模块"""

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM Trace Analysis Report</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #1a1a2e; margin-bottom: 20px; border-bottom: 2px solid #4a90d9; padding-bottom: 10px; }}
        h2 {{ color: #2d2d44; margin: 20px 0 10px; }}
        h3 {{ color: #3d3d54; margin: 15px 0 8px; }}
        .stats-card {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; display: flex; gap: 30px; }}
        .stat-item {{ text-align: center; }}
        .stat-value {{ font-size: 28px; font-weight: bold; }}
        .stat-label {{ font-size: 12px; opacity: 0.9; }}
        .session-card {{ background: white; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); overflow: hidden; }}
        .session-header {{ background: #4a90d9; color: white; padding: 15px 20px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }}
        .session-header:hover {{ background: #3a7bc8; }}
        .session-header.collapsed {{ border-radius: 12px; }}
        .session-meta {{ display: flex; gap: 20px; font-size: 14px; }}
        .session-body {{ padding: 20px; }}
        .session-body.hidden {{ display: none; }}
        .iteration-block {{ border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 15px; }}
        .iteration-header {{ background: #f8f9fa; padding: 10px 15px; font-weight: bold; border-bottom: 1px solid #e0e0e0; }}
        .iteration-content {{ padding: 15px; }}
        .json-container {{ background: #f8f8f8; border: 1px solid #ddd; border-radius: 6px; padding: 15px; margin: 10px 0; }}
        .json-content {{ font-family: 'Consolas', 'Monaco', monospace; font-size: 13px; white-space: pre; overflow-x: auto; overflow-y: auto; min-height: 200px; max-height: 400px; width: 100%; resize: vertical; border: none; background: transparent; }}
        .label {{ display: inline-block; background: #e3f2fd; color: #1976d2; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-right: 10px; }}
        .label.response {{ background: #e8f5e9; color: #388e3c; }}
        .label.tool {{ background: #fff3e0; color: #f57c00; }}
        .label.reasoning {{ background: #fce4ec; color: #c2185b; }}
        .label.subagent {{ background: #f3e5f5; color: #7b1fa2; }}
        .collapsible {{ cursor: pointer; padding: 8px 12px; background: #e0e0e0; border-radius: 4px; margin-bottom: 8px; }}
        .collapsible:hover {{ background: #d0d0d0; }}
        .collapsible-content {{ display: none; }}
        .collapsible-content.expanded {{ display: block; }}
        .toggle-icon {{ font-size: 12px; transition: transform 0.2s; }}
        .toggle-icon.rotated {{ transform: rotate(90deg); }}
        .empty-message {{ text-align: center; color: #666; padding: 40px; }}
        .timestamp {{ color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>LLM Trace Analysis Report</h1>
        <div class="stats-card">
            <div class="stat-item">
                <div class="stat-value">{total_sessions}</div>
                <div class="stat-label">Sessions</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{total_requests}</div>
                <div class="stat-label">Requests</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{total_responses}</div>
                <div class="stat-label">Responses</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{total_iterations}</div>
                <div class="stat-label">Iterations</div>
            </div>
        </div>
        <h2>Sessions ({session_count})</h2>
        {sessions_html}
    </div>
    <script>
        function toggleSession(header) {{
            const body = header.nextElementSibling;
            const icon = header.querySelector('.toggle-icon');
            if (body.classList.contains('hidden')) {{
                body.classList.remove('hidden');
                icon.classList.add('rotated');
                header.classList.remove('collapsed');
            }} else {{
                body.classList.add('hidden');
                icon.classList.remove('rotated');
                header.classList.add('collapsed');
            }}
        }}
        function toggleCollapsible(element) {{
            const content = element.nextElementSibling;
            const icon = element.querySelector('.toggle-icon');
            if (content.classList.contains('expanded')) {{
                content.classList.remove('expanded');
                icon.classList.remove('rotated');
            }} else {{
                content.classList.add('expanded');
                icon.classList.add('rotated');
            }}
        }}
        document.querySelectorAll('.session-header').forEach(h => {{
            const body = h.nextElementSibling;
            if (body) body.classList.add('hidden');
            h.classList.add('collapsed');
        }});
    </script>
</body>
</html>
"""

SESSION_TEMPLATE = """
<div class="session-card">
    <div class="session-header" onclick="toggleSession(this)">
        <div>
            <span class="toggle-icon rotated">&#9654;</span>
            <strong>{session_id}</strong>
            <span class="timestamp">({start_time} - {end_time})</span>
        </div>
        <div class="session-meta">
            <span>Model: {model_name}</span>
            <span>Iterations: {total_iterations}</span>
        </div>
    </div>
    <div class="session-body">
        {iterations_html}
    </div>
</div>
"""

ITERATION_TEMPLATE = """
<div class="iteration-block">
    <div class="iteration-header">Iteration {iteration_num}</div>
    <div class="iteration-content">
        {request_html}
        {response_html}
    </div>
</div>
"""

REQUEST_TEMPLATE = """
<div>
    <span class="label">REQUEST</span>
    <span class="label {source_class}">{source_label}</span>
    <span class="timestamp">{timestamp}</span>
    <span class="char-count">{request_chars} chars</span>
    {system_prompt_html}
    <div style="margin-top: 10px;">
        <div class="collapsible" onclick="toggleCollapsible(this)">
            <span class="toggle-icon">&#9654;</span> Messages ({message_count})
            <span class="char-count">{messages_chars} chars</span>
        </div>
        <div class="collapsible-content">
            {messages_html}
        </div>
    </div>
    {tools_html}
    {new_message_html}
</div>
"""

TOOL_RESULT_TEMPLATE = """
<div style="margin-top: 10px;">
    <span class="label tool">Tool Call Results ({new_count})</span>
    <span class="char-count">{new_chars} chars</span>
    <span class="char-count" style="margin-left: 10px; color: #666;">[{tool_names}]</span>
    <div class="json-container">
        <button class="copy-btn" onclick="copyToClipboard(this, '{content_id}')">Copy</button>
        <pre class="json-content" id="{content_id}">{new_messages_json}</pre>
    </div>
</div>
"""

SYSTEM_PROMPT_TEMPLATE = """
<div style="margin-top: 10px;">
    <div class="collapsible" onclick="toggleCollapsible(this)">
        <span class="toggle-icon">&#9654;</span> System
        <span class="char-count">{char_count} chars</span>
    </div>
    <div class="collapsible-content">
        <div class="json-container">
            <button class="copy-btn" onclick="copyToClipboard(this, '{content_id}')">Copy</button>
            <pre class="json-content" id="{content_id}">{system_prompt}</pre>
        </div>
    </div>
</div>
"""

RESPONSE_TEMPLATE = """
<div style="margin-top: 15px;">
    <span class="label response">RESPONSE</span>
    <span class="label {source_class}">{source_label}</span>
    <span class="timestamp">{timestamp}</span>
    <span class="char-count">{response_chars} chars</span>
    {reasoning_html}
    {content_html}
    {tool_calls_html}
</div>
"""

REASONING_TEMPLATE = """
<div style="margin-top: 10px;">
    <span class="label reasoning">Reasoning</span>
    <span class="char-count">{char_count} chars</span>
    <div class="json-container">
        <button class="copy-btn" onclick="copyToClipboard(this, '{content_id}')">Copy</button>
        <pre class="json-content" id="{content_id}">{reasoning_content}</pre>
    </div>
</div>
"""

CONTENT_TEMPLATE = """
<div style="margin-top: 10px;">
    <span class="label">Content</span>
    <span class="char-count">{char_count} chars</span>
    <div class="json-container">
        <button class="copy-btn" onclick="copyToClipboard(this, '{content_id}')">Copy</button>
        <pre class="json-content" id="{content_id}">{content}</pre>
    </div>
</div>
"""

TOOL_CALLS_TEMPLATE = """
<div style="margin-top: 10px;">
    <span class="label tool">Tool Calls ({tool_count})</span>
    <span class="char-count">{char_count} chars</span>
    <div class="json-container">
        <button class="copy-btn" onclick="copyToClipboard(this, '{content_id}')">Copy</button>
        <pre class="json-content" id="{content_id}">{tool_calls_json}</pre>
    </div>
</div>
"""

JSON_BLOCK_TEMPLATE = """
<div class="json-container">
    <button class="copy-btn" onclick="copyToClipboard(this, '{content_id}')">Copy</button>
    <pre class="json-content" id="{content_id}">{content}</pre>
</div>
"""

EMPTY_SESSION_TEMPLATE = """
<div class="empty-message">
    No sessions found in the log file.
</div>
"""

INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM Trace Index</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #1a1a2e; margin-bottom: 20px; }}
        .stats {{ background: #667eea; color: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; }}
        .stats span {{ margin-right: 20px; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        th {{ background: #4a90d9; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 12px; border-bottom: 1px solid #e0e0e0; }}
        tr:hover {{ background: #f8f9fa; }}
        a {{ color: #4a90d9; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .model {{ color: #666; font-size: 13px; }}
        .time {{ color: #999; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>LLM Trace Analysis Index</h1>
        <div class="stats">
            <span><strong>{total_sessions}</strong> sessions</span>
            <span><strong>{total_requests}</strong> requests</span>
            <span><strong>{total_iterations}</strong> iterations</span>
        </div>
        <table>
            <tr>
                <th>Session ID</th>
                <th>Model</th>
                <th>Iterations</th>
                <th>Time</th>
                <th>Link</th>
            </tr>
            {session_rows}
        </table>
    </div>
</body>
</html>
"""

SESSION_ROW_TEMPLATE = """
<tr>
    <td><a href="{detail_file}">{session_id_short}</a></td>
    <td class="model">{model_name}</td>
    <td>{total_iterations}</td>
    <td class="time">{start_time} - {end_time}</td>
    <td><a href="{detail_file}">View Details</a></td>
</tr>
"""

SESSION_DETAIL_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Session: {session_id_short}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #4a90d9; color: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; }}
        .header h1 {{ margin-bottom: 5px; }}
        .header .meta {{ font-size: 14px; opacity: 0.9; }}
        .back-link {{ margin-bottom: 15px; }}
        .back-link a {{ color: #4a90d9; }}
        .subagents-tree {{ background: white; border-radius: 8px; padding: 15px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        .subagents-tree h3 {{ margin-bottom: 10px; color: #4a90d9; }}
        .subagent-node {{ padding: 5px 0; }}
        .subagent-node.depth-0 {{ padding-left: 0; }}
        .subagent-node.depth-1 {{ padding-left: 20px; background: #f8f9fa; }}
        .subagent-node.depth-2 {{ padding-left: 40px; background: #f0f0f0; }}
        .subagent-node.depth-3 {{ padding-left: 60px; background: #e8e8e8; }}
        .subagent-node .arrow {{ color: #888; margin-right: 5px; }}
        .iteration-block {{ border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 15px; }}
        .iteration-block.depth-1 {{ margin-left: 20px; border-left: 3px solid #7b1fa2; }}
        .iteration-block.depth-2 {{ margin-left: 40px; border-left: 3px solid #9c27b0; }}
        .iteration-block.depth-3 {{ margin-left: 60px; border-left: 3px solid #ba68c8; }}
        .iteration-header {{ background: #f8f9fa; padding: 10px 15px; font-weight: bold; border-bottom: 1px solid #e0e0e0; }}
        .iteration-content {{ padding: 15px; }}
        .json-container {{ background: #f8f8f8; border: 1px solid #ddd; border-radius: 6px; padding: 0; margin: 10px 0; overflow: hidden; position: relative; }}
        .json-content {{ font-family: 'Consolas', 'Monaco', monospace; font-size: 13px; white-space: pre-wrap; word-break: break-all; overflow-x: auto; overflow-y: auto; max-height: 400px; padding: 15px; padding-top: 35px; padding-right: 50px; margin: 0; }}
        .copy-btn {{ position: absolute; top: 8px; right: 18px; padding: 4px 8px; background: #4a90d9; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; opacity: 0.8; z-index: 10; }}
        .copy-btn:hover {{ opacity: 1; background: #3a7bc8; }}
        .copy-btn.copied {{ background: #388e3c; }}
        .label {{ display: inline-block; background: #e3f2fd; color: #1976d2; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-right: 10px; }}
        .label.response {{ background: #e8f5e9; color: #388e3c; }}
        .label.tool {{ background: #fff3e0; color: #f57c00; }}
        .label.reasoning {{ background: #fce4ec; color: #c2185b; }}
        .label.subagent {{ background: #f3e5f5; color: #7b1fa2; }}
        .label.depth-1 {{ background: #ede7f6; }}
        .label.depth-2 {{ background: #d1c4e9; }}
        .label.depth-3 {{ background: #b39ddb; }}
        .collapsible {{ cursor: pointer; padding: 8px 12px; background: #e0e0e0; border-radius: 4px; margin-bottom: 8px; }}
        .collapsible:hover {{ background: #d0d0d0; }}
        .collapsible-content {{ display: none; }}
        .collapsible-content.expanded {{ display: block; }}
        .toggle-icon {{ font-size: 12px; transition: transform 0.2s; }}
        .toggle-icon.rotated {{ transform: rotate(90deg); }}
        .timestamp {{ color: #666; font-size: 12px; }}
        .char-count {{ color: #888; font-size: 11px; background: #f0f0f0; padding: 2px 6px; border-radius: 3px; margin-left: 10px; }}
        .chain-label {{ font-size: 11px; color: #666; }}
.toggle-view-btn {{ margin-bottom: 10px; padding: 4px 12px; background: #4a90d9; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; }}
.toggle-view-btn:hover {{ background: #3a7bc8; }}
.tool-view-names {{ display: none; }}
.tool-view-names.expanded {{ display: block; }}
.tool-view-full {{ display: none; }}
.tool-view-full.expanded {{ display: block; }}
.tool-names-grid {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 10px; background: #f8f9fa; border-radius: 4px; }}
.tool-name-item {{ background: #e3f2fd; color: #1976d2; padding: 3px 8px; border-radius: 3px; font-size: 12px; font-family: monospace; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="back-link"><a href="index.html">&#8592; Back to Index</a></div>
        <div class="header">
            <h1>Session: {session_id_short}</h1>
            <div class="meta">Model: {model_name} | Iterations: {total_iterations} | {start_time} - {end_time}</div>
        </div>
        {subagents_tree_html}
        {iterations_html}
    </div>
    <script>
        function toggleCollapsible(element) {{
            const content = element.nextElementSibling;
            const icon = element.querySelector('.toggle-icon');
            if (content.classList.contains('expanded')) {{
                content.classList.remove('expanded');
                icon.classList.remove('rotated');
            }} else {{
                content.classList.add('expanded');
                icon.classList.add('rotated');
            }}
        }}
        function copyToClipboard(btn, contentId) {{
            const content = document.getElementById(contentId).textContent;
            navigator.clipboard.writeText(content).then(() => {{
                btn.textContent = 'Copied!';
                btn.classList.add('copied');
                setTimeout(() => {{
                    btn.textContent = 'Copy';
                    btn.classList.remove('copied');
                }}, 2000);
            }});
        }}
        function toggleToolView(btn, namesId, fullId) {{
            const namesDiv = document.getElementById(namesId);
            const fullDiv = document.getElementById(fullId);
            if (namesDiv.classList.contains('expanded')) {{
                namesDiv.classList.remove('expanded');
                fullDiv.classList.add('expanded');
                btn.textContent = 'Toggle: Names';
            }} else {{
                namesDiv.classList.add('expanded');
                fullDiv.classList.remove('expanded');
                btn.textContent = 'Toggle: Full';
            }}
        }}
    </script>
</body>
</html>
"""

SUBAGENT_TREE_TEMPLATE = """
<div class="subagents-tree">
    <h3>Subagents ({subagent_count})</h3>
    {tree_nodes_html}
</div>
"""

SUBAGENT_NODE_TEMPLATE = """
<div class="subagent-node depth-{depth}">
    <span class="arrow">&#8594;</span>
    <span class="chain-label">{chain_label}</span>
    <span class="char-count">{iterations} iters</span>
</div>
"""

ITERATION_DETAIL_TEMPLATE = """
<div class="iteration-block depth-{depth}">
    <div class="iteration-header">Iteration {iteration_num} {depth_indicator}</div>
    <div class="iteration-content">
        {request_html}
        {response_html}
    </div>
</div>
"""

TOOL_NAME_ITEM_TEMPLATE = """<span class="tool-name-item">{name}</span>"""

TOOLS_SECTION_TEMPLATE = """
<div style="margin-top: 10px;">
    <div class="collapsible" onclick="toggleCollapsible(this)">
        <span class="toggle-icon">&#9654;</span> Tools ({tool_count})
        <span class="char-count">{tools_chars} chars</span>
    </div>
    <div class="collapsible-content">
        <button class="toggle-view-btn" onclick="toggleToolView(this, '{names_id}', '{full_id}')">
            Toggle: Names
        </button>
        <div id="{names_id}" class="tool-view-names expanded">
            <div class="tool-names-grid">
                {tool_names_html}
            </div>
        </div>
        <div id="{full_id}" class="tool-view-full">
            {tools_html}
        </div>
    </div>
</div>
"""
