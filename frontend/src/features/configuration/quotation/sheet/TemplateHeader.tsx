import { Descriptions } from 'antd';
import type { Quotation } from '../types';
import metadata from '../templateMetadata.json';

export function TemplateHeader({ quotation }: { quotation?: Quotation | null }) {
  const value = (text?: string | null) => text || '待填写';
  return <header className="quote-template-header" aria-label="公司报价表头">
    <img src="/quotation/company-template.jpg" alt="艾索公司报价模板标头" width={2344} height={193} />
    <Descriptions bordered size="small" column={{ xs: 1, sm: 2 }} items={[
      { key: 'address', label: '我司地址', children: metadata.address },
      { key: 'sales', label: '销售经理 / 联系电话', children: value(quotation?.sales_contact) },
      { key: 'service', label: '服务电话', children: metadata.service },
      { key: 'designer', label: '设计人员 / 联系电话', children: value(quotation?.designer_contact) },
      { key: 'customer', label: '客户名称', children: value(quotation?.customer) },
      { key: 'date', label: '设计日期', children: value(quotation?.design_date) },
      { key: 'project', label: '项目名称', children: value(quotation?.project_name) },
      { key: 'room', label: '厅堂名称及尺寸面积', children: value(quotation?.room_description) },
    ]} />
  </header>;
}
