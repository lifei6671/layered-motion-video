import {Config} from '@remotion/cli/config';

Config.setVideoImageFormat('png');
Config.setColorSpace('bt709');
Config.setPixelFormat('yuv420p');
Config.setCodec('h264');
// PNG frames carry no SAR. Declare the fixed 16:9 display aspect at encoding;
// this sets square pixels without any FFmpeg motion/transition filter.
Config.overrideFfmpegCommand(({args}) => [
  ...args.slice(0, -1), '-aspect', '16:9', args[args.length - 1],
]);

// NodeNext imports use .js; resolve their TypeScript sources when bundling Studio/render.
Config.overrideWebpackConfig((config) => ({
  ...config,
  resolve: {...config.resolve, extensionAlias: {...config.resolve?.extensionAlias, '.js': ['.js', '.ts', '.tsx']}},
}));
