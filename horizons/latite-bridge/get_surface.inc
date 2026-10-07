// Bedrock Horizons fork addition. GPL-3.0, following Latite's license.
// The 0.1.3 crash dump identifies the BlockSource::getChunkAt call as unsafe.
// Do not touch game pointers or scan terrain until this build's ABI and full
// chunk-readiness contract have been established. Catching access violations
// after the call would not make the reader safe.
JsValueRef GameScriptingObject::dimensionGetSurface(JsValueRef callee, bool isConstructor, JsValueRef* arguments,
                                                    unsigned short argCount, void* callbackState) {
    if (!Chakra::VerifyArgCount(argCount, 3)) return JS_INVALID_REFERENCE;
    if (!Chakra::VerifyParameters({{arguments[1], JsNumber}, {arguments[2], JsNumber}}))
        return JS_INVALID_REFERENCE;
    JsValueRef result;
    JS::JsCreateObject(&result);
    Chakra::SetPropertyBool(result, L"available", false);
    Chakra::SetPropertyBool(result, L"known", false);
    Chakra::SetPropertyString(result, L"readiness", L"disabled");
    Chakra::SetPropertyString(result, L"reason", L"native-client-sampling-disabled");
    Chakra::SetProperty(result, L"observed", Chakra::GetNull());
    return result;
}

