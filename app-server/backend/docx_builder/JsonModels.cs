using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace KimiDocx;

public class DocRequest
{
    [JsonPropertyName("title")]
    public string Title { get; set; }

    [JsonPropertyName("org_name")]
    public string OrgName { get; set; } = "云南力诺科技有限公司";

    [JsonPropertyName("date_str")]
    public string DateStr { get; set; } = "";

    [JsonPropertyName("sections")]
    public List<DocSection> Sections { get; set; } = new();
}

public class DocSection
{
    [JsonPropertyName("title")]
    public string Title { get; set; }

    [JsonPropertyName("level")]
    public int Level { get; set; }

    [JsonPropertyName("blocks")]
    public List<DocBlock> Blocks { get; set; } = new();
}

public class DocBlock
{
    [JsonPropertyName("type")]
    public string Type { get; set; } // "paragraph", "table", "chart"

    [JsonPropertyName("text")]
    public string Text { get; set; }

    [JsonPropertyName("rows")]
    public List<List<string>> Rows { get; set; }

    [JsonPropertyName("chartType")]
    public string ChartType { get; set; }

    [JsonPropertyName("chartTitle")]
    public string ChartTitle { get; set; }
    
    [JsonPropertyName("chartData")]
    public List<List<string>> ChartData { get; set; }

    [JsonPropertyName("segments")]
    public List<DocSegment> Segments { get; set; }
}

// WHY: 含数学公式的段落会被拆分为 text/omml 交替片段，
//      C# 引擎据此生成 Word 原生数学公式节点。
public class DocSegment
{
    [JsonPropertyName("type")]
    public string Type { get; set; }  // "text" | "omml"

    [JsonPropertyName("value")]
    public string Value { get; set; }
}
