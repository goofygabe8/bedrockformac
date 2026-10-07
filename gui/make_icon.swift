import AppKit
let output = URL(fileURLWithPath: CommandLine.arguments[1])
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
func color(_ r: CGFloat,_ g: CGFloat,_ b: CGFloat) -> NSColor { NSColor(calibratedRed:r/255,green:g/255,blue:b/255,alpha:1) }
func polygon(_ points: [NSPoint], _ fill: NSColor) { let p=NSBezierPath();p.move(to:points[0]);for point in points.dropFirst(){p.line(to:point)};p.close();fill.setFill();p.fill() }
for size in [16,32,64,128,256,512,1024] {
    let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:size,pixelsHigh:size,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current=NSGraphicsContext(bitmapImageRep:rep)
    let scale=CGFloat(size)/1024
    let transform=NSAffineTransform();transform.scale(by:scale);transform.concat()
    color(20,29,20).setFill();NSBezierPath(roundedRect:NSRect(x:50,y:50,width:924,height:924),xRadius:190,yRadius:190).fill()
    polygon([NSPoint(x:185,y:685),NSPoint(x:512,y:860),NSPoint(x:840,y:685),NSPoint(x:512,y:505)],color(111,176,48))
    polygon([NSPoint(x:185,y:685),NSPoint(x:512,y:505),NSPoint(x:512,y:160),NSPoint(x:185,y:340)],color(116,78,45))
    polygon([NSPoint(x:512,y:505),NSPoint(x:840,y:685),NSPoint(x:840,y:340),NSPoint(x:512,y:160)],color(82,54,32))
    polygon([NSPoint(x:185,y:685),NSPoint(x:512,y:505),NSPoint(x:512,y:430),NSPoint(x:185,y:610)],color(83,137,35))
    polygon([NSPoint(x:512,y:505),NSPoint(x:840,y:685),NSPoint(x:840,y:610),NSPoint(x:512,y:430)],color(58,107,26))
    for i in 0..<5 { for j in 0..<5 {
        let x=CGFloat(i)*50, y=CGFloat(j)*50
        polygon([NSPoint(x:275+x+y,y:685+x*0.53-y*0.53),NSPoint(x:312+x+y,y:705+x*0.53-y*0.53),NSPoint(x:350+x+y,y:685+x*0.53-y*0.53),NSPoint(x:312+x+y,y:665+x*0.53-y*0.53)], color(CGFloat(92+(i*19+j*23)%45),CGFloat(147+(i*7+j*11)%42),35))
    }}
    for side in 0..<2 { for i in 0..<5 { for j in 0..<4 {
        let x=CGFloat(i)*57 + (side == 0 ? 205 : 525)
        let slope=side == 0 ? -0.55 : 0.55
        let y=CGFloat(j)*54 + 335 + CGFloat(i)*57*slope
        color(CGFloat((side == 0 ? 132 : 98)+(i*17+j*13)%22),CGFloat(66+(i*13+j*9)%31),35).setFill()
        NSRect(x:x,y:y,width:29,height:25).fill()
    }}}
    NSGraphicsContext.restoreGraphicsState()
    let data=rep.representation(using:.png,properties:[:])!
    if size <= 512 { try data.write(to:output.appendingPathComponent("icon_\(size)x\(size).png")) }
    if size >= 32 { try data.write(to:output.appendingPathComponent("icon_\(size/2)x\(size/2)@2x.png")) }
}
