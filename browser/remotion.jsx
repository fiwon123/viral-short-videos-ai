import React, {useLayoutEffect, useRef, useState} from "react";
import {Composition, registerRoot, staticFile, useCurrentFrame, useDelayRender} from "remotion";
import {createPainter} from "./painter.mjs";

function Picture({data, cover = false}) {
  const frame = useCurrentFrame();
  const surface = useRef(null);
  const painter = useRef(null);
  const current = useRef(frame);
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  const [handle] = useState(() => delayRender("Preparing studio artwork"));
  useLayoutEffect(() => {
    let active = true;
    createPainter(surface.current, data, staticFile).then((instance) => {
      if (!active) {
        instance.dispose();
        return;
      }
      painter.current = instance;
      instance.draw(current.current, cover);
      continueRender(handle);
    }).catch((error) => {
      if (active) cancelRender(error);
    });
    return () => {
      active = false;
      painter.current?.dispose();
      painter.current = null;
    };
  }, [data, cover, handle, continueRender, cancelRender]);
  useLayoutEffect(() => {
    current.current = frame;
    painter.current?.draw(frame, cover);
  }, [frame, cover]);
  return <canvas ref={surface} width={data.width} height={data.height} style={{display: "block"}} />;
}

registerRoot(() => <Composition
  id="ViralVideo"
  component={Picture}
  durationInFrames={1}
  width={240}
  height={240}
  fps={30}
  calculateMetadata={({props: {data}}) => ({
    durationInFrames: data.frames, width: data.width, height: data.height, fps: data.fps,
  })}
/>);
