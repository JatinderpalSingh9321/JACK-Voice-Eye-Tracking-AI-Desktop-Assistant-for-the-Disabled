const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageNumber, Header, Footer, TabStopType, TabStopPosition
} = require('docx');
const fs = require('fs');

const BLUE = "1A3A5C";
const ACCENT = "2E86C1";
const LIGHT_BLUE = "D6EAF8";
const LIGHT_GRAY = "F2F3F4";
const MID_GRAY = "BDC3C7";
const WHITE = "FFFFFF";

const border = { style: BorderStyle.SINGLE, size: 1, color: MID_GRAY };
const borders = { top: border, bottom: border, left: border, right: border };
const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

function heading1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 320, after: 160 },
    children: [new TextRun({ text, bold: true, size: 30, color: BLUE, font: "Arial" })]
  });
}

function heading2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 120 },
    children: [new TextRun({ text, bold: true, size: 24, color: ACCENT, font: "Arial" })]
  });
}

function body(text, opts = {}) {
  return new Paragraph({
    spacing: { before: 80, after: 80 },
    children: [new TextRun({ text, size: 22, font: "Arial", ...opts })]
  });
}

function bullet(text, bold_prefix = null) {
  const runs = [];
  if (bold_prefix) {
    runs.push(new TextRun({ text: bold_prefix + " ", bold: true, size: 22, font: "Arial" }));
  }
  runs.push(new TextRun({ text: bold_prefix ? text : text, size: 22, font: "Arial" }));
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 60, after: 60 },
    children: runs
  });
}

function spacer(pts = 160) {
  return new Paragraph({ spacing: { before: pts, after: 0 }, children: [new TextRun("")] });
}

function sectionDivider(label) {
  return new Paragraph({
    spacing: { before: 200, after: 100 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 1 } },
    children: [new TextRun({ text: label.toUpperCase(), bold: true, size: 20, color: ACCENT, font: "Arial", allCaps: true })]
  });
}

function tableHeaderCell(text, widthDXA) {
  return new TableCell({
    borders,
    width: { size: widthDXA, type: WidthType.DXA },
    shading: { fill: BLUE, type: ShadingType.CLEAR },
    margins: { top: 100, bottom: 100, left: 140, right: 140 },
    children: [new Paragraph({
      children: [new TextRun({ text, bold: true, size: 20, font: "Arial", color: WHITE })]
    })]
  });
}

function tableBodyCell(text, widthDXA, shade = false, bold = false) {
  return new TableCell({
    borders,
    width: { size: widthDXA, type: WidthType.DXA },
    shading: { fill: shade ? LIGHT_GRAY : WHITE, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 140, right: 140 },
    children: [new Paragraph({
      children: [new TextRun({ text, size: 20, font: "Arial", bold })]
    })]
  });
}

function statusCell(text, color, bgColor, widthDXA) {
  return new TableCell({
    borders,
    width: { size: widthDXA, type: WidthType.DXA },
    shading: { fill: bgColor, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 140, right: 140 },
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text, size: 20, font: "Arial", bold: true, color })]
    })]
  });
}

const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } }
        }]
      }
    ]
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, font: "Arial", color: BLUE },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0 }
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: ACCENT },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 }
      }
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 }
      }
    },
    headers: {
      default: new Header({
        children: [
          new Paragraph({
            border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: ACCENT, space: 1 } },
            spacing: { after: 100 },
            children: [
              new TextRun({ text: "ANTIGRAVITY  |  Project Work Plan", bold: true, size: 20, font: "Arial", color: BLUE }),
              new TextRun({ text: "  \u2014  EOG-Based Assistive Navigation System", size: 20, font: "Arial", color: "888888" })
            ]
          })
        ]
      })
    },
    footers: {
      default: new Footer({
        children: [
          new Paragraph({
            border: { top: { style: BorderStyle.SINGLE, size: 4, color: ACCENT, space: 1 } },
            spacing: { before: 100 },
            tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
            children: [
              new TextRun({ text: "Confidential \u2014 Internal Use Only", size: 18, font: "Arial", color: "888888" }),
              new TextRun({ text: "\tPage ", size: 18, font: "Arial", color: "888888" }),
              new TextRun({ children: [PageNumber.CURRENT], size: 18, font: "Arial", color: "888888" })
            ]
          })
        ]
      })
    },
    children: [

      // TITLE BLOCK
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 200, after: 60 },
        children: [new TextRun({ text: "ANTIGRAVITY", bold: true, size: 52, font: "Arial", color: BLUE })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 40 },
        children: [new TextRun({ text: "EOG-Based Assistive Navigation System", size: 26, font: "Arial", color: ACCENT })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 20 },
        children: [new TextRun({ text: "Project Work Plan  |  Revised Scope  |  2025", size: 20, font: "Arial", color: "888888" })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: ACCENT, space: 1 } },
        spacing: { before: 20, after: 200 },
        children: [new TextRun({ text: "Team: Jatinderpal Singh | Sambhav Manhas", size: 20, font: "Arial", color: "888888" })]
      }),

      spacer(100),

      // OVERVIEW
      heading1("1. Project Overview"),
      body("Antigravity is an EOG (Electrooculography) based assistive navigation system that allows users to control a computer entirely through eye signals \u2014 blinks and winks. The system replaces traditional motor imagery EEG with reliable, affordable eye-movement detection and integrates Claude AI to intelligently interpret signals and execute OS-level navigation actions."),
      spacer(60),
      body("This is a pivot from the original motor imagery BCI concept. The new system is fully achievable with existing hardware and produces a working, demonstrable product.", { italics: true, color: "555555" }),

      spacer(120),

      // WHAT'S NEW
      heading1("2. What Is New in This Version"),

      heading2("2.1 Navigation via EOG signals only"),
      body("The system no longer attempts motor imagery (EEG). All control is through eye-based EOG signals which are 10\u201350x stronger and far more reliable with consumer-grade hardware."),
      spacer(40),

      heading2("2.2 Claude AI as the decision engine"),
      body("Instead of hard-coded if/else logic, each detected signal is sent to Claude API with the current UI state. Claude decides what action to take based on context \u2014 making the system adaptive and intelligent rather than rigid."),
      spacer(40),

      heading2("2.3 Scanning interface for navigation"),
      body("A custom scanning UI cycles through navigation options (folder, browser, camera, notepad, image viewer, etc.) automatically. The user blinks to select the highlighted item \u2014 no direction signal required."),
      spacer(40),

      heading2("2.4 Full OS navigation capability"),
      body("The system can open folders, images, camera, browser, and other applications using Python subprocess calls \u2014 fulfilling the complete navigation requirement specified by the project supervisor."),

      spacer(120),

      // SIGNAL MAPPING TABLE
      heading1("3. Signal Mapping"),
      spacer(40),

      new Table({
        width: { size: 9080, type: WidthType.DXA },
        columnWidths: [2000, 2500, 2500, 2080],
        rows: [
          new TableRow({
            tableHeader: true,
            children: [
              tableHeaderCell("Signal", 2000),
              tableHeaderCell("EOG Detection", 2500),
              tableHeaderCell("Navigation Action", 2500),
              tableHeaderCell("Reliability", 2080),
            ]
          }),
          new TableRow({ children: [
            tableBodyCell("Single blink", 2000, false, true),
            tableBodyCell("Large spike on Fp1, both eyes", 2500),
            tableBodyCell("Select highlighted item", 2500),
            statusCell("High", "27500A", "EAF3DE", 2080)
          ]}),
          new TableRow({ children: [
            tableBodyCell("Double blink", 2000, true, true),
            tableBodyCell("Two spikes within 600ms", 2500, true),
            tableBodyCell("Go back / cancel", 2500, true),
            statusCell("High", "27500A", "EAF3DE", 2080)
          ]}),
          new TableRow({ children: [
            tableBodyCell("Wink left", 2000, false, true),
            tableBodyCell("Asymmetric deflection, left side", 2500),
            tableBodyCell("Move highlight to previous", 2500),
            statusCell("Medium", "633806", "FAEEDA", 2080)
          ]}),
          new TableRow({ children: [
            tableBodyCell("Wink right", 2000, true, true),
            tableBodyCell("Asymmetric deflection, right side", 2500, true),
            tableBodyCell("Move highlight to next", 2500, true),
            statusCell("Medium", "633806", "FAEEDA", 2080)
          ]}),
        ]
      }),

      spacer(120),

      // NEW DATA COLLECTION
      heading1("4. New Data Collection Plan"),
      body("The previous motor imagery data (C3/C4 electrodes) is not used. A completely fresh data collection session is required for the new EOG-based approach."),
      spacer(60),

      heading2("4.1 Electrode placement (new)"),
      bullet("IN+ on Fp1 (left forehead, above left eyebrow)"),
      bullet("IN\u2212 on left earlobe (referential setup, not bipolar)"),
      bullet("GND on right earlobe"),
      body("This referential Fp1 setup captures clean unipolar EOG signals and clearly distinguishes left wink, right wink, and bilateral blink.", { color: "555555", italics: true }),
      spacer(60),

      heading2("4.2 Data collection protocol"),
      bullet("Run test_blink_wink.py \u2014 subject 002 (new session, separate from old data)"),
      bullet("75 trials total: 25 blinks, 25 wink-left, 25 wink-right"),
      bullet("Pygame window guides the user with eye icons on screen"),
      bullet("Rest 5 seconds between each block to reduce eye fatigue"),
      bullet("Collect minimum 2 sessions on different days for robustness"),
      spacer(60),

      heading2("4.3 Data quality checks"),
      bullet("Inspect raw signal in real time \u2014 blink peaks should exceed 3x baseline amplitude"),
      bullet("Reject trials where electrode contact was poor (flat or noisy signal)"),
      bullet("Ensure DC offset is accounted for before peak detection threshold is set"),
      spacer(60),

      heading2("4.4 Model retraining"),
      bullet("Train new eog_1ch_model.pkl using train_eog_1ch.py on fresh Fp1 data"),
      bullet("Target: \u226580% cross-validation accuracy before integration"),
      bullet("Test live with mouse_control_eog.py in simulate mode first, then real hardware"),

      spacer(120),

      // WORK PLAN TABLE
      heading1("5. Phase-wise Work Plan"),
      spacer(40),

      new Table({
        width: { size: 9080, type: WidthType.DXA },
        columnWidths: [1200, 2800, 3200, 1880],
        rows: [
          new TableRow({
            tableHeader: true,
            children: [
              tableHeaderCell("Phase", 1200),
              tableHeaderCell("Task", 2800),
              tableHeaderCell("Key Deliverable", 3200),
              tableHeaderCell("Status", 1880),
            ]
          }),
          new TableRow({ children: [
            tableBodyCell("Phase 1", 1200, false, true),
            tableBodyCell("New electrode setup + data collection (Fp1 referential)", 2800),
            tableBodyCell("75+ labelled EOG trials saved as subject_002", 3200),
            statusCell("Pending", "712B13", "FAECE7", 1880)
          ]}),
          new TableRow({ children: [
            tableBodyCell("Phase 2", 1200, true, true),
            tableBodyCell("Train new 1-channel EOG classifier", 2800, true),
            tableBodyCell("eog_1ch_model.pkl with \u226580% accuracy", 3200, true),
            statusCell("Pending", "712B13", "FAECE7", 1880)
          ]}),
          new TableRow({ children: [
            tableBodyCell("Phase 3", 1200, false, true),
            tableBodyCell("Build scanning navigation UI", 2800),
            tableBodyCell("Python UI that cycles through 6 OS actions", 3200),
            statusCell("In progress", "0C447C", "E6F1FB", 1880)
          ]}),
          new TableRow({ children: [
            tableBodyCell("Phase 4", 1200, true, true),
            tableBodyCell("Integrate Claude API decision layer", 2800, true),
            tableBodyCell("Claude interprets signal + context, returns action", 3200, true),
            statusCell("In progress", "0C447C", "E6F1FB", 1880)
          ]}),
          new TableRow({ children: [
            tableBodyCell("Phase 5", 1200, false, true),
            tableBodyCell("Connect EOG model output to navigation + OS execution", 2800),
            tableBodyCell("Full pipeline: blink \u2192 Claude \u2192 open folder/browser/camera", 3200),
            statusCell("Pending", "712B13", "FAECE7", 1880)
          ]}),
          new TableRow({ children: [
            tableBodyCell("Phase 6", 1200, true, true),
            tableBodyCell("Demo preparation + fallback keyboard mode", 2800, true),
            tableBodyCell("Recorded demo video + keyboard backup for exam day", 3200, true),
            statusCell("Pending", "712B13", "FAECE7", 1880)
          ]}),
        ]
      }),

      spacer(120),

      // TECH STACK
      heading1("6. Technology Stack"),
      spacer(40),

      new Table({
        width: { size: 9080, type: WidthType.DXA },
        columnWidths: [2200, 3200, 3680],
        rows: [
          new TableRow({
            tableHeader: true,
            children: [
              tableHeaderCell("Layer", 2200),
              tableHeaderCell("Component", 3200),
              tableHeaderCell("Detail", 3680),
            ]
          }),
          new TableRow({ children: [
            tableBodyCell("Hardware", 2200, false, true),
            tableBodyCell("BioAmp EXG Pill + Arduino R4 Minima", 3200),
            tableBodyCell("Single pill, Fp1 referential, COM7, 500Hz", 3680),
          ]}),
          new TableRow({ children: [
            tableBodyCell("Signal processing", 2200, true, true),
            tableBodyCell("Python + scipy + numpy", 3200, true),
            tableBodyCell("Bandpass filter, peak detection, threshold classifier", 3680, true),
          ]}),
          new TableRow({ children: [
            tableBodyCell("ML model", 2200, false, true),
            tableBodyCell("SVM (eog_1ch_model.pkl)", 3200),
            tableBodyCell("3-class: blink / wink_left / wink_right", 3680),
          ]}),
          new TableRow({ children: [
            tableBodyCell("AI decision layer", 2200, true, true),
            tableBodyCell("Claude API (claude-sonnet-4-5)", 3200, true),
            tableBodyCell("Signal + UI state \u2192 action decision in natural language", 3680, true),
          ]}),
          new TableRow({ children: [
            tableBodyCell("Navigation UI", 2200, false, true),
            tableBodyCell("Python (tkinter or pygame scanning UI)", 3200),
            tableBodyCell("Auto-cycling highlight, 6 OS actions", 3680),
          ]}),
          new TableRow({ children: [
            tableBodyCell("OS execution", 2200, true, true),
            tableBodyCell("Python subprocess", 3200, true),
            tableBodyCell("Opens folder, browser, camera, notepad, image viewer", 3680, true),
          ]}),
        ]
      }),

      spacer(120),

      // DEMO SCRIPT
      heading1("7. Demo Script for Examination"),
      body("The demo will show a complete end-to-end navigation session without any manual mouse or keyboard input (except for the keyboard fallback if hardware fails)."),
      spacer(60),

      heading2("Demo sequence"),
      bullet("Start scanning UI \u2014 6 options highlighted one by one automatically"),
      bullet("Wink right twice \u2192 highlight moves to Open Browser"),
      bullet("Blink once \u2192 browser opens (Chrome/Edge)"),
      bullet("Wink left \u2192 highlight moves back to Open Folder"),
      bullet("Blink once \u2192 File Explorer opens"),
      bullet("Double blink \u2192 returns to main menu"),
      bullet("Wink right \u2192 highlight moves to Open Camera"),
      bullet("Blink once \u2192 Windows Camera app launches"),
      spacer(60),

      heading2("Fallback plan"),
      bullet("Keyboard keys (B, W, X, D) simulate blink/wink signals for demo if hardware glitches"),
      bullet("Pre-recorded demo video as backup if live hardware fails entirely"),

      spacer(120),

      // KEY RISKS
      heading1("8. Key Risks and Mitigations"),
      spacer(40),

      new Table({
        width: { size: 9080, type: WidthType.DXA },
        columnWidths: [3040, 3040, 3000],
        rows: [
          new TableRow({
            tableHeader: true,
            children: [
              tableHeaderCell("Risk", 3040),
              tableHeaderCell("Mitigation", 3040),
              tableHeaderCell("Fallback", 3000),
            ]
          }),
          new TableRow({ children: [
            tableBodyCell("Poor electrode contact during demo", 3040),
            tableBodyCell("Wet scalp, press firmly, use tape to hold electrode", 3040),
            tableBodyCell("Keyboard simulation mode", 3000),
          ]}),
          new TableRow({ children: [
            tableBodyCell("Wink detection unreliable", 3040, true),
            tableBodyCell("Switch to auto-scan mode \u2014 only blink needed", 3040, true),
            tableBodyCell("Auto-scan removes need for wink signals", 3000, true),
          ]}),
          new TableRow({ children: [
            tableBodyCell("Claude API call fails or is slow", 3040),
            tableBodyCell("Add local fallback decision logic in Python", 3040),
            tableBodyCell("Direct signal-to-action mapping without API", 3000),
          ]}),
          new TableRow({ children: [
            tableBodyCell("Insufficient training data", 3040, true),
            tableBodyCell("Collect 2+ sessions, augment with noise injection", 3040, true),
            tableBodyCell("Use pre-existing eog_3class_model.pkl", 3000, true),
          ]}),
        ]
      }),

      spacer(120),

      // CLOSING
      new Paragraph({
        spacing: { before: 200, after: 100 },
        border: {
          top: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 1 },
          bottom: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 1 }
        },
        children: [
          new TextRun({ text: "This document is a living plan \u2014 update phase statuses as work progresses. All previous motor imagery data and EEG-based models are deprecated and not part of this revised scope.", size: 20, font: "Arial", italics: true, color: "555555" })
        ]
      }),

    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync('Antigravity_WorkPlan.docx', buffer);
  console.log('Done - saved to Antigravity_WorkPlan.docx');
});
