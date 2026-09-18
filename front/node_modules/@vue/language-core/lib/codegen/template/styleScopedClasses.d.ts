import type { Code, IRBlock } from '../../types';
export declare const references: WeakMap<IRBlock, [version: string, [className: string, offset: number][]]>;
export declare function generateStyleScopedClassReference(block: IRBlock, className: string, offset: number, fullStart?: number): Generator<Code>;
