// draw.io adds file metadata and viewport offsets when serializing a host update.
// They do not represent a user edit and must not create an extra undo entry.
const fileMetadata = new Set(["host", "modified", "agent", "etag", "version"]);
const viewportAttributes = new Set(["dx", "dy"]);
export function drawingIdentity(xml: string): string {
  if (!xml) return "";
  const document = new DOMParser().parseFromString(xml, "application/xml");
  if (document.querySelector("parsererror"))
    throw new Error("图纸 XML 无法解析");
  function nodeValue(node: Element): unknown {
    const attributes = Array.from(node.attributes)
      .filter((a) => !(node.tagName === "mxfile" && fileMetadata.has(a.name)))
      .filter(
        (a) =>
          !(node.tagName === "mxGraphModel" && viewportAttributes.has(a.name)),
      )
      .map((a) => [a.name, a.value])
      .sort(([a], [b]) => a.localeCompare(b));
    const children = Array.from(node.children).map(nodeValue);
    return [
      node.tagName,
      attributes,
      children,
      children.length ? "" : node.textContent?.trim(),
    ];
  }
  return JSON.stringify(nodeValue(document.documentElement));
}
