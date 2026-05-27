import win32gui
import win32com.client
import pythoncom
import win32process
import win32thread
import os
import time

def get_active_explorer_window():
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass
        
    active_hwnd = win32gui.GetForegroundWindow()
    is_explorer = False
    if active_hwnd:
        class_name = win32gui.GetClassName(active_hwnd)
        if class_name in ("CabinetWClass", "ExploreWClass"):
            is_explorer = True
            
    # Fallback: Find top-most visible File Explorer window if current foreground is not Explorer
    if not is_explorer:
        print("Active window is not explorer. Finding top-most visible File Explorer...")
        explorer_hwnds = []
        def enum_cb(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                cls = win32gui.GetClassName(hwnd)
                if cls in ("CabinetWClass", "ExploreWClass"):
                    explorer_hwnds.append(hwnd)
        win32gui.EnumWindows(enum_cb, None)
        
        if explorer_hwnds:
            active_hwnd = explorer_hwnds[0]
            is_explorer = True
            print(f"Found explorer HWND: {active_hwnd}. Attempting to focus...")
            
            # Try to bring it to foreground using AttachThreadInput
            try:
                fore_hwnd = win32gui.GetForegroundWindow()
                if fore_hwnd and fore_hwnd != active_hwnd:
                    fore_thread = win32process.GetWindowThreadProcessId(fore_hwnd)[0]
                    app_thread = win32thread.GetCurrentThreadId()
                    if fore_thread != app_thread:
                        try:
                            win32thread.AttachThreadInput(fore_thread, app_thread, True)
                            win32gui.ShowWindow(active_hwnd, 5) # SW_SHOW
                            win32gui.SetForegroundWindow(active_hwnd)
                            win32thread.AttachThreadInput(fore_thread, app_thread, False)
                            print("Focus successfully transferred using AttachThreadInput.")
                        except Exception as e2:
                            print(f"AttachThreadInput method failed: {e2}")
                            # Fallback to direct set
                            win32gui.ShowWindow(active_hwnd, 5)
                            win32gui.SetForegroundWindow(active_hwnd)
                else:
                    win32gui.ShowWindow(active_hwnd, 5)
                    win32gui.SetForegroundWindow(active_hwnd)
            except Exception as e:
                print(f"Direct SetForegroundWindow failed: {e}")
        else:
            print("No visible File Explorer windows found.")
            return None, None

    try:
        active_title = win32gui.GetWindowText(active_hwnd)
        print(f"Selected Explorer HWND: {active_hwnd}, Title: '{active_title}'")
        target_tab_name = None
        if " - File Explorer" in active_title:
            tab_part = active_title.split(" - File Explorer")[0]
            if " and " in tab_part:
                right_part = tab_part.split(" and ")[-1]
                if "more tab" in right_part:
                    target_tab_name = tab_part.rsplit(" and ", 1)[0]
            if not target_tab_name:
                target_tab_name = tab_part
        
        print(f"Target tab name parsed: '{target_tab_name}'")
        shell = win32com.client.Dispatch("Shell.Application")
        windows = shell.Windows()
        matching_tabs = []
        for i in range(windows.Count):
            w = windows.Item(i)
            try:
                if w.hwnd == active_hwnd:
                    matching_tabs.append(w)
            except Exception:
                continue
                
        if not matching_tabs:
            print("No matching shell window found for the HWND.")
            return None, None
            
        if len(matching_tabs) == 1:
            print(f"Matched single tab: '{matching_tabs[0].LocationName}'")
            return matching_tabs[0], matching_tabs[0].Document
            
        if target_tab_name:
            for w in matching_tabs:
                if w.LocationName.lower() == target_tab_name.lower():
                    print(f"Matched tab by name: '{w.LocationName}'")
                    return w, w.Document
                    
        print(f"Defaulting to first tab: '{matching_tabs[0].LocationName}'")
        return matching_tabs[0], matching_tabs[0].Document
    except Exception as e:
        print(f"Error in get_active_explorer_window: {e}")
        
    return None, None

def test_selection():
    w, doc = get_active_explorer_window()
    if not doc:
        print("Failed to get document.")
        return
        
    folder = doc.Folder
    items = folder.Items()
    count = items.Count
    print(f"Total items in folder: {count}")
    if count > 0:
        # Select first item
        item = items.Item(0)
        print(f"Selecting item 0: '{item.Name}'")
        doc.SelectItem(item, 29)
        print("Selection command sent.")
    else:
        print("Folder is empty.")

if __name__ == "__main__":
    test_selection()
