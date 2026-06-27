# custom_templates.py
# High-precision HTML templates for administrative document styles.

COMPLAINT_HTML = """<h1>投 诉 登 记 表</h1>
<table noborder="true" style="width: 100%; margin-bottom: 8px; font-size: 14px;">
  <tbody>
    <tr>
      <td noborder="true" style="text-align: left; background: transparent; border: none; padding: 0;">登记单位：________________________________</td>
      <td noborder="true" style="text-align: right; background: transparent; border: none; padding: 0;">编号：________________________________</td>
    </tr>
  </tbody>
</table>
<table border="1" style="width: 100%; border-collapse: collapse; border: 2px solid #000000; table-layout: fixed; font-size: 14px; text-align: center;">
  <colgroup>
    <col style="width: 10%;" />
    <col style="width: 15%;" />
    <col style="width: 25%;" />
    <col style="width: 15%;" />
    <col style="width: 17.5%;" />
    <col style="width: 17.5%;" />
  </colgroup>
  <tbody>
    <tr style="height: 40px;">
      <td rowspan="4" style="font-weight: bold; border: 1px solid #000000; padding: 8px; writing-mode: vertical-rl; text-orientation: upright; letter-spacing: 4px;">投诉人</td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">姓名</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系电话</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>
    </tr>
    <tr style="height: 40px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">证件类型</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">证件号码</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>
    </tr>
    <tr style="height: 40px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系地址</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="4"></td>
    </tr>
    <tr style="height: 40px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">是否同意公示投诉信息</td>
      <td style="border: 1px solid #000000; padding: 8px;">□是&nbsp;&nbsp;&nbsp;&nbsp;□否</td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">是否同意委托调解</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2">□是&nbsp;&nbsp;&nbsp;&nbsp;□否</td>
    </tr>
    <tr style="height: 40px;">
      <td rowspan="2" style="font-weight: bold; border: 1px solid #000000; padding: 8px; writing-mode: vertical-rl; text-orientation: upright; letter-spacing: 4px;">被投诉人</td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">名称（姓名）</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系人</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>
    </tr>
    <tr style="height: 40px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">地址</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系电话</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>
    </tr>
    <tr style="height: 180px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 12px; writing-mode: vertical-rl; text-orientation: upright; line-height: 1.5; letter-spacing: 2px;">消费者权益争议事实依据</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="5"></td>
    </tr>
    <tr style="height: 140px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 12px; writing-mode: vertical-rl; text-orientation: upright; line-height: 1.5; letter-spacing: 2px;">投诉请求</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="5"></td>
    </tr>
    <tr style="height: 80px;">
      <td style="border: 1px solid #000000; padding: 12px; text-align: left; vertical-align: bottom;" colspan="3">
        投诉人（签字）：<br/><br/>
        <div style="text-align: right; padding-right: 20px;">年&nbsp;&nbsp;&nbsp;&nbsp;月&nbsp;&nbsp;&nbsp;&nbsp;日</div>
      </td>
      <td style="border: 1px solid #000000; padding: 12px; text-align: left; vertical-align: bottom;" colspan="3">
        经办人（签字）：<br/><br/>
        <div style="text-align: right; padding-right: 20px;">年&nbsp;&nbsp;&nbsp;&nbsp;月&nbsp;&nbsp;&nbsp;&nbsp;日</div>
      </td>
    </tr>
  </tbody>
</table>
<div style="margin-top: 12px; font-size: 12px; line-height: 1.6; text-align: left;">
  <div>注：1. 本表格适用于市场监督管理部门对消费者通过电话、信函、上门等方式提起投诉 of 消费者权益争议的登记。</div>
  <div>&nbsp;&nbsp;&nbsp;&nbsp;2. 消费者通过非现场方式提起投诉的，无须在投诉人一栏签字。</div>
  <div>&nbsp;&nbsp;&nbsp;&nbsp;3. 消费者权益争议事实依据应当包括：消费者购买、使用商品或者接受服务的时间、地点、内容、涉及金额、消费者权益争议情况等具体事实及相应证明材料。</div>
  <div>&nbsp;&nbsp;&nbsp;&nbsp;4. 投诉请求应当包括：消费者主张修理、重作、更换、退货、补足商品数量、退还货款和服务费用、赔偿损失等具体请求。</div>
</div>"""

REPORT_HTML = """<h1>举 报 登 记 表</h1>
<table noborder="true" style="width: 100%; margin-bottom: 8px; font-size: 14px;">
  <tbody>
    <tr>
      <td noborder="true" style="text-align: left; background: transparent; border: none; padding: 0;">登记单位：________________________________</td>
      <td noborder="true" style="text-align: right; background: transparent; border: none; padding: 0;">编号：________________________________</td>
    </tr>
  </tbody>
</table>
<table border="1" style="width: 100%; border-collapse: collapse; border: 2px solid #000000; table-layout: fixed; font-size: 14px; text-align: center;">
  <colgroup>
    <col style="width: 10%;" />
    <col style="width: 15%;" />
    <col style="width: 25%;" />
    <col style="width: 15%;" />
    <col style="width: 17.5%;" />
    <col style="width: 17.5%;" />
  </colgroup>
  <tbody>
    <tr style="height: 40px;">
      <td rowspan="2" style="font-weight: bold; border: 1px solid #000000; padding: 8px; writing-mode: vertical-rl; text-orientation: upright; letter-spacing: 4px;">举报人</td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">姓名</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系电话</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>
    </tr>
    <tr style="height: 40px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系地址</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">身份证件号码</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="2"></td>
    </tr>
    <tr style="height: 40px;">
      <td rowspan="2" style="font-weight: bold; border: 1px solid #000000; padding: 8px; writing-mode: vertical-rl; text-orientation: upright; letter-spacing: 4px;">被举报人</td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">名称（姓名）</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="4"></td>
    </tr>
    <tr style="height: 40px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">地址</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="4"></td>
    </tr>
    <tr style="height: 200px;">
      <td style="font-weight: bold; border: 1px solid #000000; padding: 12px; writing-mode: vertical-rl; text-orientation: upright; line-height: 1.5; letter-spacing: 2px;">涉嫌违反市场监督管理法律、法规、规章的具体线索 and 相应的事实依据</td>
      <td style="border: 1px solid #000000; padding: 8px;" colspan="5"></td>
    </tr>
    <tr style="height: 80px;">
      <td style="border: 1px solid #000000; padding: 12px; text-align: left; vertical-align: bottom;" colspan="3">
        举报人（签字）：<br/><br/>
        <div style="text-align: right; padding-right: 20px;">年&nbsp;&nbsp;&nbsp;&nbsp;月&nbsp;&nbsp;&nbsp;&nbsp;日</div>
      </td>
      <td style="border: 1px solid #000000; padding: 12px; text-align: left; vertical-align: bottom;" colspan="3">
        经办人（签字）：<br/><br/>
        <div style="text-align: right; padding-right: 20px;">年&nbsp;&nbsp;&nbsp;&nbsp;月&nbsp;&nbsp;&nbsp;&nbsp;日</div>
      </td>
    </tr>
  </tbody>
</table>
<div style="margin-top: 12px; font-size: 12px; line-height: 1.6; text-align: left;">
  <div>注: 1. 本表格适用于市场监督管理部门对举报人通过电话、信函、上门等方式提起举报的登记。</div>
  <div>&nbsp;&nbsp;&nbsp;&nbsp;2. 举报人可以匿名举报，但应当提供具体涉嫌违法线索 and 相应的事实依据，并对举报内容的真实性负责。举报人实名举报的，还应当提供真实的身份信息。</div>
  <div>&nbsp;&nbsp;&nbsp;&nbsp;3. 通过非现场方式提出举报的，无须在举报人一栏签字。</div>
</div>"""

SEND_NOTICE_HTML = """<p style="text-align: right; font-size: 14px; font-family: SimSun, serif; margin: 0;">文书式样三</p>
<h1 style="text-align: center; font-size: 26px; font-family: SimHei, sans-serif; font-weight: bold; margin-top: 12px; margin-bottom: 24px;">投 诉 / 举 报 分 送 通 知 书</h1>
<p style="text-align: center; font-size: 14px; font-family: SimSun, serif; margin-bottom: 30px;">________市监________〔&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;〕第________号</p>
<p style="text-align: left; font-size: 14px; font-family: SimSun, serif; font-weight: bold; margin-bottom: 12px;">________________________：</p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif;">现转去 ________________ 于 ________ 年 ____ 月 ____ 日关于 ________________ 的投诉/举报。请你局按照《市场监督管理投诉举报处理办法》的规定依法予以处理，并将处理结果于 ________ 年 ____ 月 ____ 日前报告我局。</p>
<p style="text-indent: 2em; text-align: left; line-height: 2; font-size: 14px; font-family: SimSun, serif;">附：相关材料 ________ 份，共 ________ 页。</p>
<table noborder="true" style="width: 100%; margin-top: 60px; background: transparent; border: none;">
  <tbody>
    <tr>
      <td noborder="true" style="width: 45%;"></td>
      <td noborder="true" style="width: 55%; text-align: right; background: transparent; border: none; font-size: 14px; font-family: SimSun, serif; padding: 0; line-height: 1.8;">
        ________________市场监督管理局（印章）<br/>
        ________年____月____日
      </td>
    </tr>
  </tbody>
</table>
<hr style="border: none; border-top: 1px solid #000000; margin-top: 60px; margin-bottom: 12px;" />
<div style="font-size: 12px; line-height: 1.6; text-align: left; font-family: SimSun, serif; color: #333333;">
  注：本通知书适用于省级或者地市级市场监督管理部门或者其设立的 12315 工作机构将收到的投诉/举报分送下级市场监督管理部门处理。
</div>"""

PROVIDE_IDENTITY_HTML = """<p style="text-align: right; font-size: 14px; font-family: SimSun, serif; margin: 0;">文书式样四</p>
<h1 style="text-align: center; font-size: 26px; font-family: SimHei, sans-serif; font-weight: bold; margin-top: 12px; margin-bottom: 24px;">限期提供身份证明材料通知书</h1>
<p style="text-align: center; font-size: 14px; font-family: SimSun, serif; margin-bottom: 30px;">________市监________〔&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;〕第________号</p>
<p style="text-align: left; font-size: 14px; font-family: SimSun, serif; font-weight: bold; margin-bottom: 12px;">________________________：</p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif;">根据《中华人民共和国消费者权益保护法实施条例》第四十六条第一款的规定，消费者和经营者发生消费争议向市场监督管理部门或者其他有关行政部门投诉的，应当提供真实身份信息等材料。</p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif;">根据《市场监督管理投诉举报处理办法》第十条第三款的规定，请你在 ________ 年 ____ 月 ____ 日前向我局提供以下身份证明材料。</p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif;">逾期未提供或提供虚假材料的，我局将根据《市场监督管理投诉举报处理办法>第十条、第十六条的规定，对投诉依法不予受理。</p>
<p style="text-indent: 2em; text-align: left; line-height: 2; font-size: 14px; font-family: SimSun, serif;">联系电话：________________；通信地址：________________。</p>
<table noborder="true" style="width: 100%; margin-top: 60px; background: transparent; border: none;">
  <tbody>
    <tr>
      <td noborder="true" style="width: 45%;"></td>
      <td noborder="true" style="width: 55%; text-align: right; background: transparent; border: none; font-size: 14px; font-family: SimSun, serif; padding: 0; line-height: 1.8;">
        ________________市场监督管理局（印章）<br/>
        ________年____月____日
      </td>
    </tr>
  </tbody>
</table>
<hr style="border: none; border-top: 1px solid #000000; margin-top: 60px; margin-bottom: 12px;" />
<div style="font-size: 12px; line-height: 1.6; text-align: left; font-family: SimSun, serif; color: #333333;">
  注：1. 本通知书适用于投诉人未提供真实身份信息，市场监督管理部门通知投诉人限期提供身份证明材料。<br/>
  &nbsp;&nbsp;&nbsp;&nbsp;2. 本通知书中“联系电话”“通信地址”指接收限期提供身份证明材料的市场监督管理部门地址及联系电话。
</div>"""

ACCEPT_NOTICE_HTML = """<p style="text-align: right; font-size: 14px; font-family: SimSun, serif; margin: 0;">文书式样五</p>
<h1 style="text-align: center; font-size: 26px; font-family: SimHei, sans-serif; font-weight: bold; margin-top: 12px; margin-bottom: 24px;">投 诉 受 理 决 定 书</h1>
<p style="text-align: center; font-size: 14px; font-family: SimSun, serif; margin-bottom: 30px;">________市监________〔&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;〕第________号</p>
<p style="text-align: left; font-size: 14px; font-family: SimSun, serif; font-weight: bold; margin-bottom: 12px;">________________________：</p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif;">我局于 ________ 年 ____ 月 ____ 日收到你关于 ________________ 的投诉。经审查，符合《市场监督管理投诉举报处理办法》规定的受理条件，我局决定受理。</p>
<p style="text-indent: 2em; text-align: left; line-height: 2; font-size: 14px; font-family: SimSun, serif;">联系人：________________；联系电话：________________。</p>
<p style="text-indent: 2em; text-align: left; line-height: 2; font-size: 14px; font-family: SimSun, serif;">特此告知。</p>
<table noborder="true" style="width: 100%; margin-top: 60px; background: transparent; border: none;">
  <tbody>
    <tr>
      <td noborder="true" style="width: 45%;"></td>
      <td noborder="true" style="width: 55%; text-align: right; background: transparent; border: none; font-size: 14px; font-family: SimSun, serif; padding: 0; line-height: 1.8;">
        ________________市场监督管理局（印章）<br/>
        ________年____月____日
      </td>
    </tr>
  </tbody>
</table>
<hr style="border: none; border-top: 1px solid #000000; margin-top: 60px; margin-bottom: 12px;" />
<div style="font-size: 12px; line-height: 1.6; text-align: left; font-family: SimSun, serif; color: #333333;">
  注：1. 本决定书适用于市场监督管理部门对投诉作出受理决定，并告知投诉人受理情况。<br/>
  &nbsp;&nbsp;&nbsp;&nbsp;2. 本决定书中“联系人”“联系电话”指市场监督管理部门负责处理投诉的工作人员及其联系电话。<br/>
  &nbsp;&nbsp;&nbsp;&nbsp;3. 本决定书可以通过互联网、电话、短信、电子邮件、信函等方式告知。
</div>"""

REJECT_NOTICE_HTML = """<p style="text-align: right; font-size: 14px; font-family: SimSun, serif; margin: 0;">文书式样六</p>
<h1 style="text-align: center; font-size: 26px; font-family: SimHei, sans-serif; font-weight: bold; margin-top: 12px; margin-bottom: 24px;">投诉不予受理决定书</h1>
<p style="text-align: center; font-size: 14px; font-family: SimSun, serif; margin-bottom: 30px;">________市监________〔&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;〕第________号</p>
<p style="text-align: left; font-size: 14px; font-family: SimSun, serif; font-weight: bold; margin-bottom: 12px;">________________________：</p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif;">我局于 ________ 年 ____ 月 ____ 日收到你关于 ________________ 的投诉。经审查，属以下第〔 &nbsp;&nbsp;&nbsp;&nbsp; 〕项情形，依据《市场监督管理投诉举报处理办法》第十六条的规定，我局决定不予受理。</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（一）投诉事项不属于市场监督管理部门职责，或者本行政机关不具有处理权限的；</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（二）法院、仲裁机构、市场监督管理部门或者其他行政机关、消费者协会已经受理或者处理过同一消费者权益争议的；</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（三）不是为生活消费需要购买、使用商品或者接受服务，或者不能证明与被投诉人之间存在消费者权益争议的；</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（四）除法律另有规定外，投诉人知道或者应当知道自己的权益受到被投诉人侵害之日起超过三年的；</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（五）未提供本办法第十条第一款、第十一条规定的材料，或者提供虚假材料的；</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（六）冒用他人名义或者拒不配合市场监督管理部门核验真实身份信息的；</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（七）法律、法规、规章规定不予受理的其他情形。</p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif;">你还可以按照《中华人民共和国消费者权益保护法》第三十九条规定的其他途径解决消费者权益争议。</p>
<p style="text-indent: 2em; text-align: left; line-height: 2; font-size: 14px; font-family: SimSun, serif;">特此告知。</p>
<table noborder="true" style="width: 100%; margin-top: 40px; background: transparent; border: none;">
  <tbody>
    <tr>
      <td noborder="true" style="width: 45%;"></td>
      <td noborder="true" style="width: 55%; text-align: right; background: transparent; border: none; font-size: 14px; font-family: SimSun, serif; padding: 0; line-height: 1.8;">
        ________________市场监督管理局（印章）<br/>
        ________年____月____日
      </td>
    </tr>
  </tbody>
</table>
<hr style="border: none; border-top: 1px solid #000000; margin-top: 40px; margin-bottom: 12px;" />
<div style="font-size: 12px; line-height: 1.6; text-align: left; font-family: SimSun, serif; color: #333333;">
  注：1. 本决定书适用于市场监督管理部门对投诉作出不予受理决定，并告知投诉人不予受理情况。<br/>
  &nbsp;&nbsp;&nbsp;&nbsp;2. 本决定书可以通过互联网、电话、短信、电子邮件、信函等方式告知。
</div>"""

MEDIATION_NOTICE_HTML = """<p style="text-align: right; font-size: 14px; font-family: SimSun, serif; margin: 0;">文书式样七</p>
<h1 style="text-align: center; font-size: 26px; font-family: SimHei, sans-serif; font-weight: bold; margin-top: 12px; margin-bottom: 24px;">投 诉 调 解 通 知 书</h1>
<p style="text-align: center; font-size: 14px; font-family: SimSun, serif; margin-bottom: 30px;">________市监________〔&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;〕第________号</p>
<p style="text-align: left; font-size: 14px; font-family: SimSun, serif; font-weight: bold; margin-bottom: 12px;">________________________：</p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif;">关于 ________________ 的投诉，我局已经受理，根据《市场监督管理投诉举报处理办法》的规定，现组织双方当事人进行现场调解。请于 ________ 年 ____ 月 ____ 日 ____ 时到 ________________ 参加调解。无正当理由不参加调解的，我局将依法终止调解。</p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif;">请携带以下材料：1. 身份证明材料；2. ________________________________。</p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif;">如果您认为调解人员是投诉人或者被投诉人的近亲属或者有其他利害关系，可能影响公正处理投诉的，可以自收到本通知书之日起 ____ 日内对调解人员提出回避申请。</p>
<p style="text-indent: 2em; text-align: left; line-height: 2; font-size: 14px; font-family: SimSun, serif;">调解人员：________________；联系电话：________________。</p>
<p style="text-indent: 2em; text-align: left; line-height: 2; font-size: 14px; font-family: SimSun, serif;">特此通知。</p>
<table noborder="true" style="width: 100%; margin-top: 40px; background: transparent; border: none;">
  <tbody>
    <tr>
      <td noborder="true" style="width: 45%;"></td>
      <td noborder="true" style="width: 55%; text-align: right; background: transparent; border: none; font-size: 14px; font-family: SimSun, serif; padding: 0; line-height: 1.8;">
        ________________市场监督管理局（印章）<br/>
        ________年____月____日
      </td>
    </tr>
  </tbody>
</table>
<hr style="border: none; border-top: 1px solid #000000; margin-top: 40px; margin-bottom: 12px;" />
<div style="font-size: 12px; line-height: 1.6; text-align: left; font-family: SimSun, serif; color: #333333;">
  注：1. 本通知书适用于市场监督管理部门通知投诉人和被投诉人参加现场调解。<br/>
  &nbsp;&nbsp;&nbsp;&nbsp;2. 本通知书中“调解人员”“联系电话”指主持调解的工作人员及其联系电话。<br/>
  &nbsp;&nbsp;&nbsp;&nbsp;3. 本通知书可以通过互联网、电话、短信、电子邮件、信函等方式告知。
</div>"""

TERMINATE_MEDIATION_HTML = """<p style="text-align: right; font-size: 14px; font-family: SimSun, serif; margin: 0;">文书式样八</p>
<h1 style="text-align: center; font-size: 26px; font-family: SimHei, sans-serif; font-weight: bold; margin-top: 12px; margin-bottom: 24px;">投诉终止调解决定书</h1>
<p style="text-align: center; font-size: 14px; font-family: SimSun, serif; margin-bottom: 30px;">________市监________〔&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;〕第________号</p>
<p style="text-align: left; font-size: 14px; font-family: SimSun, serif; font-weight: bold; margin-bottom: 12px;">________________________：</p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif;">经审查，关于 ________________ 投诉的调解过程中出现以下第〔 &nbsp;&nbsp;&nbsp;&nbsp; 〕项情形，依据《市场监督管理投诉举报处理办法》第二十三条第一款的规定，我局决定终止调解。</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（一）投诉人撤回投诉或者双方自行和解的；</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（二）投诉人、被投诉人无正当理由不参加调解，或者明确拒绝调解的；</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（三）经组织调解，投诉人或者被投诉人明确表示无法达成调解协议的；</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（四）投诉人与被投诉人对鉴定、检测费用承担无法协商一致的；</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（五）自投诉受理之日起六十日内投诉人和被投诉人未能达成调解协议的；</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（六）市场监督管理部门受理投诉后，发现存在本办法第十六条、第四十二条规定情形的；</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（七）投诉人、被投诉人死亡或者主体资格灭失的；</p>
<p style="text-indent: 2em; text-align: justify; line-height: 1.8; font-size: 14px; font-family: SimSun, serif;">（八）法律、法规、规章规定的应当终止调解的其他情形。</p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif;">投诉人、被投诉人对市场监督管理部门作出的终止调解决定、调解结果不服的，可以按照《中华人民共和国消费者权益保护法》第三十九条规定，通过民事诉讼、仲裁等其他途径解决消费者权益争议。</p>
<p style="text-indent: 2em; text-align: left; line-height: 2; font-size: 14px; font-family: SimSun, serif;">特此告知。</p>
<table noborder="true" style="width: 100%; margin-top: 40px; background: transparent; border: none;">
  <tbody>
    <tr>
      <td noborder="true" style="width: 45%;"></td>
      <td noborder="true" style="width: 55%; text-align: right; background: transparent; border: none; font-size: 14px; font-family: SimSun, serif; padding: 0; line-height: 1.8;">
        ________________市场监督管理局（印章）<br/>
        ________年____月____日
      </td>
    </tr>
  </tbody>
</table>
<hr style="border: none; border-top: 1px solid #000000; margin-top: 40px; margin-bottom: 12px;" />
<div style="font-size: 12px; line-height: 1.6; text-align: left; font-family: SimSun, serif; color: #333333;">
  注：1. 本决定书适用于市场监督管理部门对投诉作出终止调解决定，并告知投诉人和被投诉人终止调解情况。<br/>
  &nbsp;&nbsp;&nbsp;&nbsp;2. 本决定书可以通过互联网、电话、短信、电子邮件、信函等方式告知。
</div>"""

MEDIATION_AGREEMENT_HTML = """<p style="text-align: right; font-size: 14px; font-family: SimSun, serif; margin: 0;">文书式样九</p>
<h1 style="text-align: center; font-size: 26px; font-family: SimHei, sans-serif; font-weight: bold; margin-top: 12px; margin-bottom: 24px;">投 诉 调 解 书</h1>
<p style="text-align: center; font-size: 14px; font-family: SimSun, serif; margin-bottom: 30px;">________市监________〔&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;〕第________号</p>
<table border="1" style="width: 100%; border-collapse: collapse; border: 2px solid #000000; table-layout: fixed; font-size: 14px; text-align: left; margin-bottom: 20px;">
  <tbody>
    <tr>
      <td style="font-weight: bold; width: 20%; border: 1px solid #000000; padding: 8px;">投诉人</td>
      <td style="width: 30%; border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; width: 20%; border: 1px solid #000000; padding: 8px;">联系电话</td>
      <td style="width: 30%; border: 1px solid #000000; padding: 8px;"></td>
    </tr>
    <tr>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系地址</td>
      <td colspan="3" style="border: 1px solid #000000; padding: 8px;"></td>
    </tr>
    <tr>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">委托代理人</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系电话</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
    </tr>
    <tr>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">被投诉人</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">法定代表人</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
    </tr>
    <tr>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">经营场所</td>
      <td colspan="3" style="border: 1px solid #000000; padding: 8px;"></td>
    </tr>
    <tr>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">委托代理人</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
      <td style="font-weight: bold; border: 1px solid #000000; padding: 8px;">联系电话</td>
      <td style="border: 1px solid #000000; padding: 8px;"></td>
    </tr>
  </tbody>
</table>
<p style="font-weight: bold; font-size: 14px; font-family: SimSun, serif; margin-top: 15px; margin-bottom: 8px;">投诉内容及投诉请求：</p>
<p style="border: 1px solid #000000; padding: 12px; min-height: 80px; font-size: 14px; font-family: SimSun, serif;"></p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif; margin-top: 15px;">根据《市场监督管理投诉举报处理办法》有关规定，本局组织双方当事人进行调解，双方自愿达成如下协议：</p>
<p style="border: 1px solid #000000; padding: 12px; min-height: 100px; font-size: 14px; font-family: SimSun, serif;"></p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif; margin-top: 15px;">本调解书经双方当事人签字后生效。调解书生效后，一方当事人未履行的，另一方当事人可以依据《中华人民共和国消费者权益保护法》第三十九条规定，通过民事诉讼、仲裁等其他途径解决消费者权益争议。</p>
<table noborder="true" style="width: 100%; margin-top: 40px; background: transparent; border: none; font-size: 14px; font-family: SimSun, serif;">
  <tbody>
    <tr>
      <td noborder="true" style="width: 50%; padding: 8px; border: none;">投诉人（签名）：</td>
      <td noborder="true" style="width: 50%; padding: 8px; border: none;">被投诉人（签名）：</td>
    </tr>
    <tr>
      <td noborder="true" style="width: 50%; padding: 8px; border: none;">调解人员（签名）：</td>
      <td noborder="true" style="width: 50%; padding: 8px; border: none; text-align: right;">
        ________________市场监督管理局（印章）<br/>
        ________年____月____日
      </td>
    </tr>
  </tbody>
</table>
<hr style="border: none; border-top: 1px solid #000000; margin-top: 40px; margin-bottom: 12px;" />
<div style="font-size: 12px; line-height: 1.6; text-align: left; font-family: SimSun, serif; color: #333333;">
  注：1. 本调解书适用于市场监督管理部门组织投诉人和被投诉人现场调解并达成调解协议。调解协议已经即时履行或者双方同意不制作调解书的，可以不制作调解书，市场监督管理部门应当做好调解记录备查。<br/>
  &nbsp;&nbsp;&nbsp;&nbsp;2. 本调解书由投诉人和被投诉人双方签字或者盖章，并加盖市场监督管理部门印章，交投诉人和被投诉人各执一份，市场监督管理部门留存一份归档。<br/>
  &nbsp;&nbsp;&nbsp;&nbsp;3. 投诉人和被投诉人委托他人参加调解的，被委托人应当出具授权委托书和身份证明。
</div>"""

REPORT_RESULT_HTML = """<p style="text-align: right; font-size: 14px; font-family: SimSun, serif; margin: 0;">文书式样十</p>
<h1 style="text-align: center; font-size: 26px; font-family: SimHei, sans-serif; font-weight: bold; margin-top: 12px; margin-bottom: 24px;">举报处理结果告知书</h1>
<p style="text-align: center; font-size: 14px; font-family: SimSun, serif; margin-bottom: 30px;">________市监________〔&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;〕第________号</p>
<p style="text-align: left; font-size: 14px; font-family: SimSun, serif; font-weight: bold; margin-bottom: 12px;">________________________：</p>
<p style="text-indent: 2em; text-align: justify; line-height: 2; font-size: 14px; font-family: SimSun, serif;">关于 ________________ 的举报，我局已依法处理。根据《________________》第 ________ 条规定，现将处理结果告知如下：</p>
<p style="border: 1px solid #000000; padding: 12px; min-height: 120px; font-size: 14px; font-family: SimSun, serif;"></p>
<p style="text-indent: 2em; text-align: left; line-height: 2; font-size: 14px; font-family: SimSun, serif;">特此告知。</p>
<table noborder="true" style="width: 100%; margin-top: 60px; background: transparent; border: none;">
  <tbody>
    <tr>
      <td noborder="true" style="width: 45%;"></td>
      <td noborder="true" style="width: 55%; text-align: right; background: transparent; border: none; font-size: 14px; font-family: SimSun, serif; padding: 0; line-height: 1.8;">
        ________________市场监督管理局（印章）<br/>
        ________年____月____日
      </td>
    </tr>
  </tbody>
</table>
<hr style="border: none; border-top: 1px solid #000000; margin-top: 60px; margin-bottom: 12px;" />
<div style="font-size: 12px; line-height: 1.6; text-align: left; font-family: SimSun, serif; color: #333333;">
  注：1. 本告知书适用于市场监督管理部门依据法律、法规、规章的明确规定，将举报处理结果告知举报人。<br/>
  &nbsp;&nbsp;&nbsp;&nbsp;2. 本告知书可以通过互联网、电话、短信、电子邮件、信函等方式告知。
</div>"""
