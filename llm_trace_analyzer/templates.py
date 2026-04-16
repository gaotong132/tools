"""HTML模板模块"""

SESSION_DETAIL_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Session: {session_id_short}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlightjs-line-numbers.js/2.8.0/highlightjs-line-numbers.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #4a90d9; color: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; }}
        .header h1 {{ margin-bottom: 5px; }}
        .header .meta {{ font-size: 14px; opacity: 0.9; }}
        .back-link {{ margin-bottom: 15px; }}
        .back-link a {{ color: #4a90d9; }}
        .iteration-block {{ border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 15px; }}
        .iteration-header {{ background: #f8f9fa; padding: 10px 15px; font-weight: bold; border-bottom: 1px solid #e0e0e0; }}
        .iteration-content {{ padding: 15px; }}
        .json-container {{ background: #282c34; border-radius: 6px; margin: 10px 0; overflow: hidden; }}
        .json-container pre {{ margin: 0; padding: 15px; overflow-x: auto; overflow-y: auto; max-height: 500px; }}
        .json-container code {{ font-family: 'Consolas', 'Monaco', monospace; font-size: 13px; line-height: 1.5; }}
        .hljs {{ background: #282c34; color: #abb2bf; }}
        .hljs-ln-numbers {{ padding-right: 15px; color: #636d83; border-right: 1px solid #3e4451; }}
        .hljs-ln-line {{ padding-left: 15px; }}
        .label {{ display: inline-block; background: #e3f2fd; color: #1976d2; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-right: 10px; }}
        .label.response {{ background: #e8f5e9; color: #388e3c; }}
        .label.tool {{ background: #fff3e0; color: #f57c00; }}
        .label.reasoning {{ background: #fce4ec; color: #c2185b; }}
        .collapsible {{ cursor: pointer; padding: 8px 12px; background: #e0e0e0; border-radius: 4px; margin-bottom: 8px; }}
        .collapsible:hover {{ background: #d0d0d0; }}
        .collapsible-content {{ display: none; }}
        .collapsible-content.expanded {{ display: block; }}
        .toggle-icon {{ font-size: 12px; transition: transform 0.2s; }}
        .toggle-icon.rotated {{ transform: rotate(90deg); }}
        .timestamp {{ color: #666; font-size: 12px; }}
        .content-box {{ background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; margin: 10px 0; white-space: pre-wrap; word-break: break-word; max-height: 500px; overflow-y: auto; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="back-link"><a href="index.html">&#8592; Back to Index</a></div>
        <div class="header">
            <h1>Session: {session_id_short}</h1>
            <div class="meta">Model: {model_name} | Iterations: {total_iterations} | {start_time} - {end_time}</div>
        </div>
        {iterations_html}
    </div>
    <script>
        hljs.initLineNumbersOnLoad();
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
    </script>
</body>
</html>
"""

ITERATION_DETAIL_TEMPLATE = """
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
    <span class="timestamp">{timestamp}</span>
    <div class="collapsible" onclick="toggleCollapsible(this)">
        <span class="toggle-icon">&#9654;</span> Messages ({message_count}) + Tools ({tool_count})
    </div>
    <div class="collapsible-content">
        <div class="json-container">
            <pre><code class="language-json">{messages_json}</code></pre>
        </div>
        <div class="json-container">
            <pre><code class="language-json">{tools_json}</code></pre>
        </div>
    </div>
</div>
"""

RESPONSE_TEMPLATE = """
<div style="margin-top: 15px;">
    <span class="label response">RESPONSE</span>
    <span class="timestamp">{timestamp}</span>
    {reasoning_html}
    {content_html}
    {tool_calls_html}
</div>
"""

REASONING_TEMPLATE = """
<div style="margin-top: 10px;">
    <span class="label reasoning">Reasoning</span>
    <div class="collapsible" onclick="toggleCollapsible(this)">
        <span class="toggle-icon">&#9654;</span> Show reasoning content
    </div>
    <div class="collapsible-content">
        <div class="content-box">{reasoning_content}</div>
    </div>
</div>
"""

CONTENT_TEMPLATE = """
<div style="margin-top: 10px;">
    <span class="label">Content</span>
    <div class="content-box">{content}</div>
</div>
"""

TOOL_CALLS_TEMPLATE = """
<div style="margin-top: 10px;">
    <span class="label tool">Tool Calls ({tool_count})</span>
    <div class="json-container">
        <pre><code class="language-json">{tool_calls_json}</code></pre>
    </div>
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
