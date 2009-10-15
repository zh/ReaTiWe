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
    content += "<ul>\n";	  
    for (var i = 0; i < items.length; ++i) {
      content += '<li class="lien" style="background-image: url(http://img.tweetimag.es/i/' + 
	items[i].avatar + '_n)"><big><a href="/user/' + items[i].author + '">' + 
	items[i].name + '</a></big><div>' + items[i].content + '</div><small><a href="/entry/' +
	items[i].id + '">#' + items[i].id + '</a> from ' +  items[i].origin + ', <span>' + 
	items[i].date + ' ago</span>';
      if (items[i].replies > 0) {
        content += '; <a class="reply" href="/entry/' + items[i].id + '">' + 
          items[i].replies + ' replies</a>';
      }
      if (items[i].likes > 0) {
        content += ', <span class="like">' + items[i].likes + ' likes</span>';
      }
      content += "</small>.</li>\n";
    }
    content += "</ul>\n";	  
  }

  document.getElementById("entries").innerHTML = content;
  window.setTimeout(showStuff, 5000);
}

window.onload = showStuff;
