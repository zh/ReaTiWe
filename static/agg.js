function showStuff() {
  var req = new XMLHttpRequest();
  req.open("GET", "/items", true);
  req.onreadystatechange = function() {
    if (req.readyState != 4) {
      return;
    }
    gotStuff(req.status, req.responseText);
  };
  req.send(null);
}

function gotStuff(status, text) {
  if (status != 200) {
    window.setTimeout(showStuff, 5000);
    return;
  }

  var content = "";
  var items = eval(text);
  if (items.length == 0) {
    content = "Nothing yet.\n"
  } else {
    for (var i = 0; i < items.length; ++i) {
      content += '<p><span class="poster"><a href="/user/' + items[i].author + 
           '">' + items[i].author + '</a></span> ' + items[i].content +
	   ' <a href="/entry/' + items[i].id + '">' +  
	   items[i].date + " ago.</a></p>\n";    
    }
  }

  document.getElementById("entries").innerHTML = content;
  window.setTimeout(showStuff, 5000);
}

window.onload = showStuff;
