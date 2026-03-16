import React from "react";
import { Composition } from "remotion";
import { TerminalDemo } from "./TerminalDemo";

const FPS = 30;
const SCENE_DURATION = 110;
const TOTAL_SCENES = 7;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="TerminalDemo"
        component={TerminalDemo}
        durationInFrames={SCENE_DURATION * TOTAL_SCENES}
        fps={FPS}
        width={960}
        height={540}
      />
    </>
  );
};
