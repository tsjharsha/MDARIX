import { Panel } from "../../admin/console/charts";
import { errorText, useResource } from "../../customer-admin/shared";
import type { Trees } from "../decisionTrees";
import { TreeAnswer } from "./TreeAnswer";

export { TREE_NAMES, treePlace, type TreeMarket, type TreeNode, type TreePath, type Trees } from "../decisionTrees";

/**
 * Decision trees (0.10.75, Release C part C3; the questionnaire itself from 0.10.83, D2): one tree per market, built
 * from the decision guides (their locked wording and test matrix). A complaint is answered on its market's tree, and
 * the outcome and Sign sit beside it. The address carries the market and the complaint
 * (/app/decision-trees?market=US&complaint=<id>), so a complaint's page opens its tree.
 */
export function DecisionTreesSection() {
  const all = useResource<Trees>("/api/v1/decision-trees");
  if (!all.data)
    return (
      <Panel eyebrow="Decision trees" title="Is it reportable, and by when?" source={all}>
        {all.state === "error" && <p className="ac-muted">{errorText(all.error, "The trees could not be read.")}</p>}
      </Panel>
    );
  return <TreeAnswer trees={all.data} />;
}
