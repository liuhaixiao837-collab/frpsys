"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.generateTemplate = generateTemplate;
const codeFeatures_1 = require("../codeFeatures");
const names_1 = require("../names");
const utils_1 = require("../utils");
const merge_1 = require("../utils/merge");
function* generateTemplate(options, ctx, selfType) {
    yield* generateSetupExposed(options, ctx);
    yield* generateTemplateCtx(options, ctx, selfType);
    yield* generateTemplateComponents(options, ctx);
    yield* generateTemplateDirectives(options, ctx);
    if (options.templateAndStyleCodes.length) {
        yield* options.templateAndStyleCodes;
    }
}
function* generateTemplateCtx({ vueCompilerOptions, templateAndStyleTypes, scriptSetupRanges, fileName }, ctx, selfType) {
    const exps = [];
    const emitTypes = [];
    const propTypes = [];
    if (vueCompilerOptions.petiteVueExtensions.some(ext => fileName.endsWith(ext))) {
        exps.push(`globalThis`);
    }
    if (selfType) {
        exps.push(`{} as InstanceType<${names_1.names.PickNotAny}<typeof ${selfType}, new () => {}>>`);
    }
    else {
        exps.push(`{} as import('${vueCompilerOptions.lib}').ComponentPublicInstance`);
    }
    if (templateAndStyleTypes.has(names_1.names.StyleModules)) {
        exps.push(`{} as ${names_1.names.StyleModules}`);
    }
    if (scriptSetupRanges?.defineEmits) {
        emitTypes.push(`typeof ${scriptSetupRanges.defineEmits.name ?? names_1.names.emit}`);
    }
    if (scriptSetupRanges?.defineModel.length) {
        emitTypes.push(`typeof ${names_1.names.modelEmit}`);
    }
    if (emitTypes.length) {
        yield `type ${names_1.names.EmitProps} = ${names_1.names.EmitsToProps}<${names_1.names.NormalizeEmits}<${emitTypes.join(` & `)}>>${utils_1.endOfLine}`;
        exps.push(`{} as { $emit: ${emitTypes.join(` & `)} }`);
    }
    if (scriptSetupRanges?.defineProps) {
        propTypes.push(`typeof ${scriptSetupRanges.defineProps.name ?? names_1.names.props}`);
    }
    if (scriptSetupRanges?.defineModel.length) {
        propTypes.push(names_1.names.ModelProps);
    }
    if (emitTypes.length) {
        propTypes.push(names_1.names.EmitProps);
    }
    if (propTypes.length) {
        exps.push(`{} as { $props: ${propTypes.join(` & `)} }`);
        exps.push(`{} as ${propTypes.join(` & `)}`);
    }
    if (ctx.generatedTypes.has(names_1.names.SetupExposed)) {
        exps.push(`{} as ${names_1.names.SetupExposed}`);
    }
    yield `const ${names_1.names.ctx} = `;
    yield* (0, merge_1.generateSpreadMerge)(...exps);
    yield utils_1.endOfLine;
}
function* generateTemplateComponents({ vueCompilerOptions, script, scriptRanges }, ctx) {
    const types = [];
    if (ctx.generatedTypes.has(names_1.names.SetupExposed)) {
        types.push(names_1.names.SetupExposed);
    }
    if (script && scriptRanges?.exportDefault?.options?.components) {
        const { components } = scriptRanges.exportDefault.options;
        yield `const ${names_1.names.componentsOption} = `;
        yield* (0, utils_1.generateSfcBlockSection)(script, components.start, components.end, codeFeatures_1.codeFeatures.navigation);
        yield utils_1.endOfLine;
        types.push(`typeof ${names_1.names.componentsOption}`);
    }
    yield `type ${names_1.names.LocalComponents} = ${types.length ? types.join(` & `) : `{}`}${utils_1.endOfLine}`;
    yield `type ${names_1.names.GlobalComponents} = ${vueCompilerOptions.target >= 3.5
        ? `import('${vueCompilerOptions.lib}').GlobalComponents`
        : `import('${vueCompilerOptions.lib}').GlobalComponents & Pick<typeof import('${vueCompilerOptions.lib}'), 'Transition' | 'TransitionGroup' | 'KeepAlive' | 'Suspense' | 'Teleport'>`}${utils_1.endOfLine}`;
    yield `let ${names_1.names.components}!: ${names_1.names.LocalComponents} & ${names_1.names.GlobalComponents}${utils_1.endOfLine}`;
    yield `let ${names_1.names.intrinsics}!: ${vueCompilerOptions.target >= 3.3
        ? `import('${vueCompilerOptions.lib}/jsx-runtime').JSX.IntrinsicElements`
        : `globalThis.JSX.IntrinsicElements`}${utils_1.endOfLine}`;
}
function* generateTemplateDirectives({ vueCompilerOptions, script, scriptRanges }, ctx) {
    const types = [];
    if (ctx.generatedTypes.has(names_1.names.SetupExposed)) {
        types.push(names_1.names.SetupExposed);
    }
    if (script && scriptRanges?.exportDefault?.options?.directives) {
        const { directives } = scriptRanges.exportDefault.options;
        yield `const ${names_1.names.directivesOption} = `;
        yield* (0, utils_1.generateSfcBlockSection)(script, directives.start, directives.end, codeFeatures_1.codeFeatures.navigation);
        yield utils_1.endOfLine;
        types.push(`${names_1.names.ResolveDirectives}<typeof ${names_1.names.directivesOption}>`);
    }
    yield `type ${names_1.names.LocalDirectives} = ${types.length ? types.join(` & `) : `{}`}${utils_1.endOfLine}`;
    yield `let ${names_1.names.directives}!: ${names_1.names.LocalDirectives} & import('${vueCompilerOptions.lib}').GlobalDirectives${utils_1.endOfLine}`;
}
function* generateSetupExposed({ vueCompilerOptions, exposed }, ctx) {
    if (!exposed.size) {
        return;
    }
    ctx.generatedTypes.add(names_1.names.SetupExposed);
    yield `type ${names_1.names.SetupExposed} = import('${vueCompilerOptions.lib}').ShallowUnwrapRef<{${utils_1.newLine}`;
    for (const bindingName of exposed) {
        const token = Symbol(bindingName.length);
        yield ['', undefined, 0, { __linkedToken: token }];
        yield `${bindingName}: typeof `;
        yield ['', undefined, 0, { __linkedToken: token }];
        yield bindingName;
        yield utils_1.endOfLine;
    }
    yield `}>${utils_1.endOfLine}`;
}
//# sourceMappingURL=template.js.map