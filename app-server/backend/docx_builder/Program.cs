using System;
using System.IO;
using System.Text.Json;
using System.Linq;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

namespace KimiDocx;

public class Program
{
    public static void Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.WriteLine("Usage: docx_builder <input.json> <output.docx>");
            return;
        }

        string inputJson = args[0];
        string outputPath = args[1];
        
        // This is where templates backgrounds would be located
        string bgDir = args.Length > 2 ? args[2] : "/app/backend/docx_builder/assets";

        var jsonOptions = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
        var request = JsonSerializer.Deserialize<DocRequest>(File.ReadAllText(inputJson), jsonOptions);

        GenerateDynamic(outputPath, request, bgDir);
    }

    public static void GenerateDynamic(string outputPath, DocRequest request, string bgDir)
    {
        using var doc = WordprocessingDocument.Create(outputPath, WordprocessingDocumentType.Document);
        var mainPart = doc.AddMainDocumentPart();
        mainPart.Document = new Document(new Body());
        var body = mainPart.Document.Body;

        DocxEngine.AddStyles(mainPart);
        DocxEngine.AddNumbering(mainPart);

        string coverImageId = DocxEngine.AddImage(mainPart, Path.Combine(bgDir, "cover_bg.png"));
        string bodyImageId = DocxEngine.AddImage(mainPart, Path.Combine(bgDir, "body_bg.png"));
        string backcoverImageId = DocxEngine.AddImage(mainPart, Path.Combine(bgDir, "backcover_bg.png"));

        DocxEngine.AddCoverSection(body, coverImageId, request);
        // We will skip TOC generation if we don't know the pages exactly, but Word updates it.
        // Let's add TOC
        DocxEngine.AddTocSection(body, bodyImageId, mainPart);

        AddDynamicContentSection(doc, body, bodyImageId, mainPart, bgDir, request);

        DocxEngine.AddBackcoverSection(body, backcoverImageId, request);
        // DocxEngine.SetUpdateFieldsOnOpen(mainPart); // Removed to prevent annoying MS Word Prompt

        doc.Save();
        Console.WriteLine($"Successfully saved {outputPath}");
    }

    private static void AddDynamicContentSection(WordprocessingDocument doc, Body body, string bodyImageId, MainDocumentPart mainPart, string bgDir, DocRequest request)
    {
        var headerPart = mainPart.AddNewPart<HeaderPart>();
        var headerId = mainPart.GetIdOfPart(headerPart);

        var headerImagePart = headerPart.AddImagePart(ImagePartType.Png);
        using (var stream = new FileStream(Path.Combine(bgDir, "body_bg.png"), FileMode.Open))
            headerImagePart.FeedData(stream);
        var headerImageId = headerPart.GetIdOfPart(headerImagePart);

        headerPart.Header = new Header(
            new Paragraph(new Run(DocxEngine.CreateFloatingBackground(headerImageId, 2, "BodyBackground"))),
            new Paragraph(
                new ParagraphProperties(
                    new Justification { Val = JustificationValues.Right },
                    new SpacingBetweenLines { Before = "0", After = "0" }
                ),
                new Run(
                    new RunProperties(new FontSize { Val = "18" }, new Color { Val = DocxEngine.Colors.Light }),
                    new Text(request.Title)
                )
            )
        );

        var footerPart = mainPart.AddNewPart<FooterPart>();
        var footerId = mainPart.GetIdOfPart(footerPart);
        var footerPara = new Paragraph(new ParagraphProperties(new Justification { Val = JustificationValues.Center }));
        footerPara.Append(DocxEngine.CreatePageNumberField());
        footerPara.Append(new Run(new Text(" / ") { Space = SpaceProcessingModeValues.Preserve }));
        footerPara.Append(DocxEngine.CreateTotalPagesField());
        footerPart.Footer = new Footer(footerPara);

        Console.WriteLine("[PROGRESS] 10 准备模板与样式...");
        int chartCounter = 1;
        int tableCounter = 1;

        int totalSections = request.Sections.Count;
        for (int i = 0; i < totalSections; i++)
        {
            var sec = request.Sections[i];
            int percentage = 10 + (int)((double)(i + 1) / totalSections * 80);
            Console.WriteLine($"[PROGRESS] {percentage} 渲染章节：{sec.Title}...");
            if (sec.Level == 1)
                body.Append(DocxEngine.CreateHeading1(sec.Title, ""));
            else if (sec.Level == 2)
                body.Append(DocxEngine.CreateHeading2(sec.Title));
            else
                body.Append(DocxEngine.CreateHeading3(sec.Title));

            foreach (var block in sec.Blocks)
            {
                if (block.Type == "paragraph")
                {
                    var pProps = new ParagraphProperties(
                        new Indentation { FirstLine = "567" }, // First line indent 2 chars
                        new SpacingBetweenLines { Line = "360", LineRule = LineSpacingRuleValues.Auto }
                    );

                    // WHY: 含数学公式的段落会有 Segments 数组（text/omml 交替），
                    //      需要逐个 segment 处理，将 OMML XML 解析为 Word 原生公式节点。
                    if (block.Segments != null && block.Segments.Count > 0)
                    {
                        var p = new Paragraph(pProps);
                        foreach (var seg in block.Segments)
                        {
                            if (seg.Type == "omml" && !string.IsNullOrEmpty(seg.Value))
                            {
                                try
                                {
                                    // WHY: 将 Python 端生成的 OMML XML 字符串解析为 OpenXML 元素。
                                    //      OpenXML SDK 的 OfficeMath 类直接接受 OuterXml 构建。
                                    var omathElement = new DocumentFormat.OpenXml.Math.OfficeMath(seg.Value);
                                    p.Append(omathElement);
                                }
                                catch (Exception ex)
                                {
                                    // WHY: OMML 解析失败时降级为纯文本，不阻断导出
                                    Console.WriteLine($"[WARN] OMML parse failed, fallback to text: {ex.Message}");
                                    p.Append(new Run(new Text(seg.Value) { Space = SpaceProcessingModeValues.Preserve }));
                                }
                            }
                            else
                            {
                                p.Append(new Run(new Text(seg.Value ?? "") { Space = SpaceProcessingModeValues.Preserve }));
                            }
                        }
                        body.Append(p);
                    }
                    else
                    {
                        // 纯文本段落（原逻辑）
                        var p = new Paragraph(pProps, new Run(new Text(block.Text ?? "")));
                        body.Append(p);
                    }
                }
                else if (block.Type == "chart")
                {
                    if (block.ChartType == "pie")
                        DocxEngine.AddPieChart(body, mainPart, block.ChartTitle);
                    else
                        DocxEngine.AddBarChart(body, mainPart); 
                }
                else if (block.Type == "table")
                {
                    DocxEngine.AddBlockTable(body, block);
                }
            }
        }
        Console.WriteLine("[PROGRESS] 100 组装结束...");

        body.Append(new Paragraph(
            new ParagraphProperties(
                new SectionProperties(
                    new SectionType { Val = SectionMarkValues.NextPage },
                    new HeaderReference { Type = HeaderFooterValues.Default, Id = headerId },
                    new FooterReference { Type = HeaderFooterValues.Default, Id = footerId },
                    new PageSize { Width = (UInt32Value)11906, Height = (UInt32Value)16838 },
                    new PageMargin { Top = 1800, Right = 1440, Bottom = 1440, Left = 1440, Header = 720, Footer = 720 }
                )
            )
        ));
    }
}
