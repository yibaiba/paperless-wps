import { Alert, App, Form, Input, InputNumber, Modal, Typography } from "antd";
import type { Configuration, IncludedAllocation, IncludedOffer } from "../types";
import { reviewIncludedAllocation } from "./includedReview";

export function IncludedReviewDialog({ configuration, allocation, offer, disabled, onApply, onClose }: {
  configuration: Configuration; allocation: IncludedAllocation; offer: IncludedOffer;
  disabled: boolean; onApply: (configuration: Configuration) => void; onClose: () => void;
}) {
  const [form] = Form.useForm();
  const { message } = App.useApp();
  return <Modal open title="重新核对已含抵扣" onCancel={onClose} onOk={() => form.submit()} okText="确认重新核对"
    okButtonProps={{ disabled: disabled || offer.status !== "pass" }}>
    <Alert type="info" showIcon title="一次提交替换原抵扣；校验失败不会删除服务端原关联。"
      description="提交后请查看工作草稿同步结果。原有采购项保持不变，系统会重新计算缺量及多余量。" />
    <Typography.Paragraph>
      {offer.name} · 采用修订 v{allocation.host_variant_revision} → 当前项目修订 v{offer.host_variant_revision}
    </Typography.Paragraph>
    <Typography.Paragraph>当前包含依据：{offer.evidence}</Typography.Paragraph>
    <Typography.Paragraph type="secondary">每单位包含 {offer.per_unit ?? "未知"}，宿主总含量 {offer.total ?? "未知"}，当前共关联 {offer.allocated}。</Typography.Paragraph>
    <Form form={form} layout="vertical" initialValues={{ quantity: allocation.quantity, evidence: "" }}
      onFinish={(values: { quantity: string; evidence: string }) => {
        try {
          onApply(reviewIncludedAllocation(configuration, { allocation, offer, ...values }));
          onClose();
        } catch (error) { message.error(error instanceof Error ? error.message : "重新核对失败"); }
      }}>
      <Form.Item name="quantity" label="重新核对的抵扣数量" rules={[{ required: true, message: "填写抵扣数量" }]}><InputNumber stringMode style={{ width: "100%" }} /></Form.Item>
      <Form.Item name="evidence" label="本次核对说明" rules={[{ required: true, whitespace: true, message: "说明为什么采用当前包含依据" }]}><Input.TextArea rows={3} /></Form.Item>
    </Form>
  </Modal>;
}
