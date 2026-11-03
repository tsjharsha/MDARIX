import { Panel } from "../../admin/console/charts";
import { errorText, useResource } from "../../customer-admin/shared";
import type { Trees } from "../decisionTrees";
import { useTabParam } from "../workspaceContext";
import { TreeAnswer } from "./TreeAnswer";
import { TreeEdit } from "./TreeEdit";

export { TREE_NAMES, treePlace, type TreeMarket, type TreeNode, type TreePath, type Trees } from "../decisionTrees";

/**
 * Decision trees (0.10.75, Release C part C3; the questionnaire itself from 0.10.83, D2): one tree per market, built
 * from the decision guides (their locked wording and test matrix). A complaint is answered on its market's tree, and
 * the outcome and Sign sit beside it. The address carries the market and the complaint
 * (/app/decision-trees?market=US&complaint=<id>), so a complaint's page opens its tree.
 */
export function DecisionTreesSection() {
  const all = useResource<Trees>("/api/v1/decision-trees");
  const [mode, setMode] = useTabParam("mode");
  if (!all.data)
    return (
      <Panel eyebrow="Decision trees" title="Is it reportable, and by when?" source={all}>
        {all.state === "error" && <p className="ac-muted">{errorText(all.error, "The trees could not be read.")}</p>}
      </Panel>
    );
  const edit = mode === "edit";
  const modes = (
    <div className="dt-modes" role="group" aria-label="Mode">
      <button type="button" aria-pressed={!edit} onClick={() => setMode(null)}>
        Answer
      </button>
      <button type="button" aria-pressed={edit} onClick={() => setMode("edit")}>
        Edit this tree
      </button>
    </div>
  );
  // While answering, the mode switch sits on the market row (0.10.84): the questions and Sign start higher.
  return (
    <div className="dt-page">
      {edit ? (
        <>
          {modes}
          <TreeEdit trees={all.data} />
        </>
      ) : (
        <TreeAnswer trees={all.data} modes={modes} />
      )}
    </div>
  );
}
