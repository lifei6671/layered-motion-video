// Explicit test-only entry. Production entry rejects artifact_kind=technical_fixture.
import {registerRoot} from 'remotion';
import {RemotionRoot} from './Root.js';
registerRoot(() => <RemotionRoot technical />);
