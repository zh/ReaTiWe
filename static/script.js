var confirmExit = false;

function confirmDelete(event) {
 if (!confirm("Are you sure you want to delete this item?")) {
  event.preventDefault();
 } else {
  confirmExit = false;
 }
}

function save() {
 confirmExit = false;
}

function init() {
 var elements = document.getElementsByClassName("delete");
 for (var i = 0; i < elements.length; i++) {
  elements[i].addEventListener("click", confirmDelete, true);
 }

 var elements = document.getElementsByClassName("save");
 if (elements.length) {
  confirmExit = true;
 }
 for (var i = 0; i < elements.length; i++) {
  elements[i].addEventListener("click", save, true);
 }
}

function exit(event) {
 if (confirmExit) {
  var tags = ["input", "textarea"];
  loop: for (var i in tags) {
   var elements = document.getElementsByTagName(tags[i]);
   for (var j = 0; j < elements.length; j++) {
    if (elements[j].defaultValue != elements[j].value) {
     event.preventDefault();
     break loop;
    }
   }
  }
 }
}

window.addEventListener("load", init, false);
window.addEventListener("beforeunload", exit, true);
