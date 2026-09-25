import { Input, Segmented, Space, Typography } from "antd";
import type { CandidateMode } from "./types";

interface Props {
  mode: CandidateMode;
  semanticInput: string;
  onModeChange: (mode: CandidateMode) => void;
  onInputChange: (value: string) => void;
  onSearch: () => void;
}

export function CandidateModeSelector(props: Props) {
  return (
    <Space orientation="vertical" style={{ width: "100%", marginBottom: 16 }}>
      <Segmented<CandidateMode>
        value={props.mode}
        options={[
          { label: "已知候选", value: "known" },
          { label: "智能查找", value: "semantic" },
          { label: "全部产品", value: "all" },
        ]}
        onChange={props.onModeChange}
      />
      <Typography.Text type="secondary">{modeHelp(props.mode)}</Typography.Text>
      {props.mode === "semantic" ? (
        <Input.Search
          placeholder="描述客户需求，例如：国产化无纸化会议服务端"
          value={props.semanticInput}
          enterButton="查找相关产品"
          onChange={(event) => props.onInputChange(event.target.value)}
          onSearch={props.onSearch}
        />
      ) : null}
    </Space>
  );
}

function modeHelp(mode: CandidateMode) {
  if (mode === "known") return "按当前系统、角色和知识版本显示候选。";
  if (mode === "semantic") return "模型只负责召回和排序，业务状态仍由搭配知识检查。";
  return "显示全部产品配置，未确认关系会标记为资料不足。";
}
