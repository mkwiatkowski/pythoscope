;;;;;;;;;;;;;;;;;;;;;
;;; Generate Python unit tests
;;;;;;;;;;;;;;;;;;;;;
;;; pythoscope.el --- generate Python unit tests for file
;;;
;;; This file is part of the pythoscope distribution and can be found at 
;;; http://pythoscope.org
;;;
;;; This file is licensed as part of pythoscope. 
;;; http://pythoscope.org/documentation#License
;;;

;;; Usage
;;; M-x  pythoscope-run-on-current-file will generate unit test for the 
;;; current file.


;;; Installation:

;; Put this file somewhere where Emacs can find it (i.e. in one of the
;; directories in your `load-path' such as `site-lisp'), optionally
;; byte-compile it, and put this in your .emacs:
;;
;;   (require 'pythoscope)


(require 'cl)

(defun string-join (separator strings)
(mapconcat 'identity strings separator))

(defun pluralize (word count)
  "Return word with a counter in singular or plural form, depending on count."
  (if (= count 1)
      (format "one %s" word)
      (format "%d %ss" count word)))

(defvar *pythoscope-process-output* "")

(defun pythoscope-generated-tests ()
  "Based on output collected in *pythoscope-process-output* return hash
mapping modules to number of tests that where added to them."
  (let ((tests (make-hash-table :test #'equal)))
    (loop for start = 0 then (match-end 0)
       while (string-match "Adding generated \\w+ to \\(.*?\\)\\.$"
                           *pythoscope-process-output* start)
       do
         (let ((modname (match-string 1 *pythoscope-process-output*)))
           (puthash modname (1+ (gethash modname tests 0)) tests)))
    tests))

(defun pythoscope-tests-hash-to-descriptions (tests)
  (loop for modname being the hash-keys in tests
     using (hash-value test-count)
     collect (format "%s for %s" (pluralize "test" test-count) modname)))

(defun pythoscope-generated-tests-summary ()
  (let ((tests (pythoscope-generated-tests)))
    (if (zerop (hash-table-count tests))
        "No tests were generated."
        (concat "Generated "
                (string-join ", " (pythoscope-tests-hash-to-descriptions tests))
                "."))))

(defun pythoscope-process-sentinel (process event)
  (when (memq (process-status process) '(signal exit))
    (let ((exit-status (process-exit-status process)))
      (if (zerop exit-status)
          (message (pythoscope-generated-tests-summary))
          (message "pythoscope[%d] exited with code %d"
                   (process-id process) exit-status)))))

(defun pythoscope-process-filter (process output)
  "Save all pythoscope output to *pythoscope-process-output* for later
inspection."
  (setq *pythoscope-process-output*
        (concat *pythoscope-process-output* output)))

(defun pythoscope-run-on-file (filename)
  "Generate tests for given file using pythoscope."
  (interactive "f")
  (setq *pythoscope-process-output* "")
  (let ((process (start-process "pythoscope-process"
                                (current-buffer)
                                "pythoscope"
                                filename)))
    (set-process-sentinel process 'pythoscope-process-sentinel)
    (set-process-filter process 'pythoscope-process-filter))
  (message "Generating tests..."))

(defun pythoscope-run-on-current-file ()
  "Generate tests for file open in the current buffer."
  (interactive)
  (let ((filename (buffer-file-name)))
    (when filename
      (pythoscope-run-on-file filename))))


(provide 'pythoscope)
