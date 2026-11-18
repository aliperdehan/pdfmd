// Use Typst's actual column region and styles. Measure with a width but without a height limit:
// a bounded measure would hide the part of an explicitly sized image that overflows its frame.
#let pdfmd-fit-picture(size, body, height, room) = scale(
  room / height * 100%, reflow: true,
  block(width: size.width, height: height, align(center, body)),
)

// Typst forwards a font diagnostic even in a successful compile. The placed zero-size marker has
// no ink or layout, and pdfmd decodes its name from the compiler diagnostics.
#let pdfmd-fit-message(name, status) = {
  for (index, part) in name.slice(1).enumerate() {
    place(text(font: "pdfmd-fit-" + status + "-" + name.first() + "-" + str(index + 1) + "-" + part,
               size: 0pt)[#sym.zws])
  }
}

#let pdfmd-fit(name, it) = layout(size => {
  let body = measure(width: size.width, it.body)
  let cap = measure(width: size.width, it.caption)
  let room = size.height - cap.height - it.gap.to-absolute()
  if room <= 0pt {
    pdfmd-fit-message(name, "c")
    it
  } else if body.height > room {
    pdfmd-fit-message(name, "s")
    let picture = pdfmd-fit-picture(size, it.body, body.height, room)
    let caption = it.caption
    let gap = v(it.gap)
    let position = caption.at("position", default: figure.caption.position)
    let content = if position == top { caption + gap + picture } else { picture + gap + caption }
    let fitted = block(breakable: false, align(center, content))
    if it.placement == none { fitted }
    else { place(it.placement, float: true, scope: it.scope, clearance: it.clearance, fitted) }
  } else {
    it
  }
})

#let pdfmd-fit-group(name, body, caption) = layout(size => {
  let height = measure(width: size.width, body).height
  let original = body + parbreak() + caption
  let space = measure(width: size.width, original).height - height
  let room = size.height - space
  if room <= 0pt {
    pdfmd-fit-message(name, "c")
    original
  } else if height > room {
    pdfmd-fit-message(name, "s")
    block(breakable: false, pdfmd-fit-picture(size, body, height, room) + parbreak() + caption)
  } else {
    original
  }
})

#let pdfmd-fit-plain(body) = layout(size => {
  show image: it => {
    let dims = measure(width: size.width, it)
    if dims.height > size.height {
      // Resolve percentage sizes in the original viewport before scaling the box that holds the image.
      scale(size.height / dims.height * 100%, reflow: true,
        box(width: dims.width, height: dims.height,
          place(left + top, block(width: size.width, height: dims.height, it))))
    } else { it }
  }
  body
})
